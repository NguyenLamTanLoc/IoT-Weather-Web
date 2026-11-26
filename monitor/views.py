import json
import logging
import math
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from django.conf import settings
from django.core.cache import cache

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import exports
from .advice import build_advice
from .models import Reading

logger = logging.getLogger(__name__)
ALLOWED_RANGES = (60, 180, 360, 1440)
OFFLINE_AFTER = timedelta(minutes=3)
FORECAST_HORIZON = 360
FORECAST_CACHE_KEY = "monitor:ai_forecast"
FORECAST_CACHE_SECONDS = 60

def _fetch_forecast(readings):
    """Call FastAPI with recent readings. Returns parsed JSON, or None on failure."""
    payload = {
        "readings": [
            {"time": r.created_at.isoformat(), "temperature": r.temperature, "humidity": r.humidity}
            for r in readings
        ],
        "fill_with_open_meteo": True,
    }
    req = urllib.request.Request(
        f"{settings.AI_SERVICE_URL}/forecast",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read())
    except (urllib.error.URLError, TimeoutError, ValueError):
        logger.exception("AI service call failed")
        return None


def _cached_forecast(readings):
    missing = object()
    result = cache.get(FORECAST_CACHE_KEY, missing)
    if result is not missing:
        return result
    result = _fetch_forecast(readings)
    cache.set(FORECAST_CACHE_KEY, result, FORECAST_CACHE_SECONDS if result else 10)
    return result


def _format_predictions(result, now):
    if not isinstance(result, dict) or not isinstance(result.get("predictions"), list):
        raise ValueError("AI service returned an invalid forecast response.")

    points = []
    for hours_ahead, prediction in enumerate(result["predictions"], start=1):
        if not isinstance(prediction, dict):
            raise ValueError("AI service returned an invalid forecast point.")
        forecast_time = datetime.fromisoformat(prediction["time"])
        if timezone.is_naive(forecast_time):
            forecast_time = timezone.make_aware(forecast_time)
        temperature = float(prediction["temperature"])
        humidity = float(prediction["humidity"])
        if not math.isfinite(temperature) or not math.isfinite(humidity) or not 0 <= humidity <= 100:
            raise ValueError("AI service returned out-of-range forecast values.")
        points.append({
            "t": int(forecast_time.timestamp() * 1000),
            "minutes_ahead": max(1, round((forecast_time - now).total_seconds() / 60)),
            "hours_ahead": hours_ahead,
            "temperature": temperature,
            "humidity": humidity,
        })
    if not points:
        raise ValueError("AI service returned no forecast points.")
    return points


def api_export(request):
    """Tải số liệu của N phút gần nhất: /api/export/?minutes=60&format=csv|json"""
    try:
        minutes = int(request.GET.get("minutes", 60))
    except ValueError:
        minutes = 60
    if minutes not in ALLOWED_RANGES:
        minutes = 60
    end = timezone.now()
    start = end - timedelta(minutes=minutes)
    rows = exports.fetch(start, end)
    name = exports.base_name(start, end)
    if request.GET.get("format") == "json":
        body, ctype, ext = exports.json_text(rows, start, end), "application/json", "json"
    else:
        body, ctype, ext = "\ufeff" + exports.csv_text(rows), "text/csv", "csv"  # BOM cho Excel
    resp = HttpResponse(body, content_type=f"{ctype}; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{name}.{ext}"'
    return resp


def dashboard(request):
    return render(request, "monitor/dashboard.html", {
        "location": settings.LOCATION_NAME,
        "ranges": [(60, "1 giờ"), (180, "3 giờ"), (360, "6 giờ"), (1440, "24 giờ")],
    })


def _downsample(readings, minutes, max_points=150):
    """Gộp trung bình theo khoảng thời gian để biểu đồ không quá dày."""
    bucket = max(1, -(-minutes // max_points)) * 60  # giây
    buckets = {}
    for r in readings:
        buckets.setdefault(int(r.created_at.timestamp() // bucket), []).append(r)
    out = []
    for key in sorted(buckets):
        rs = buckets[key]
        out.append({
            "t": int(sum(r.created_at.timestamp() for r in rs) / len(rs) * 1000),
            "temperature": round(sum(r.temperature for r in rs) / len(rs), 2),
            "humidity": round(sum(r.humidity for r in rs) / len(rs), 2),
        })
    return out


def api_dashboard(request):
    try:
        minutes = int(request.GET.get("minutes", 180))
    except ValueError:
        minutes = 180
    if minutes not in ALLOWED_RANGES:
        minutes = 180

    now = timezone.now()

    latest = Reading.objects.first()
    history = list(Reading.objects.filter(created_at__gte=now - timedelta(minutes=minutes)).order_by("created_at"))
    forecast_readings = list(
        Reading.objects.filter(created_at__gte=now - timedelta(hours=24)).order_by("created_at")
    )

    online = bool(latest and now - latest.created_at <= OFFLINE_AFTER)
    ai_result = _cached_forecast(forecast_readings) if forecast_readings and online else None
    forecast_points = []
    forecast_error = None
    if ai_result is not None:
        try:
            forecast_points = _format_predictions(ai_result, now)
        except (KeyError, TypeError, ValueError):
            logger.exception("AI service returned an invalid forecast")
            forecast_error = "Dự báo tạm thời không khả dụng."
    elif online:
        forecast_error = "Không kết nối được dịch vụ dự báo."

    if online and forecast_error:
        advice = [{
            "level": "warn",
            "title": "Dịch vụ dự báo không khả dụng",
            "detail": "Chưa thể phân tích 6 giờ tới. Kiểm tra kết nối tới dịch vụ AI.",
        }]
    else:
        advice = build_advice(latest if online else None, forecast_points)

    return JsonResponse({
        "now": int(now.timestamp() * 1000),
        "online": online,
        "decimals": settings.SENSOR_PROFILES[settings.SENSOR_TYPE]["decimals"],
        "location": settings.LOCATION_NAME,
        "latest": latest and {
            "t": int(latest.created_at.timestamp() * 1000),
            "temperature": round(latest.temperature, 1),
            "humidity": round(latest.humidity, 1),
            "device": latest.device,
        },
        "history": _downsample(history, minutes),
        "forecast": {
            "model": "LSTM + ARIMA + Random Forest",
            "horizon": FORECAST_HORIZON,
            "points": forecast_points,
            "error": forecast_error,
        },
        "advice": advice,
    })


@csrf_exempt
@require_POST
def api_ingest(request):
    """ESP32 gửi: POST JSON {"temperature": 28.5, "humidity": 71.2, "device": "esp32-01"}"""
    if request.headers.get("X-API-Key") != settings.INGEST_API_KEY:
        return JsonResponse({"error": "Sai khoá API"}, status=401)
    try:
        data = json.loads(request.body)
        temp, hum = float(data["temperature"]), float(data["humidity"])
    except (ValueError, KeyError, TypeError):
        return JsonResponse({"error": "Cần JSON có temperature và humidity (số)"}, status=400)
    if not (-40 <= temp <= 85 and 0 <= hum <= 100):
        return JsonResponse({"error": "Giá trị ngoài khoảng hợp lệ"}, status=400)
    r = Reading.objects.create(device=str(data.get("device", "esp32-01"))[:40], temperature=temp, humidity=hum)
    try:
        exports.export_previous_hour()
    except Exception:  # xuất file lỗi không được làm hỏng việc nhận số liệu
        logger.exception("Không xuất được file giờ trước")
    return JsonResponse({"id": r.id}, status=201)
