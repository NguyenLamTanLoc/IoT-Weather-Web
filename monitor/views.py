import json
import logging
import math
import urllib.error
import urllib.request
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.paginator import Paginator
from django.core.cache import cache

from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import exports
from .advice import build_advice
from .models import AlertSetting, Reading

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
        by_model = prediction.get("by_model") or {}
        temps = [temperature] + [float(v["temperature"]) for v in by_model.values()]
        hums = [humidity] + [float(v["humidity"]) for v in by_model.values()]
        points.append({
            "t_lo": min(temps), "t_hi": max(temps), "h_lo": min(hums), "h_hi": max(hums),
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
    light = request.GET.get("light") == "1"  # trang không cần dự báo thì bỏ qua cuộc gọi AI
    ai_result = _cached_forecast(forecast_readings) if forecast_readings and online and not light else None
    forecast_points = []
    forecast_error = None
    if ai_result is not None:
        try:
            forecast_points = _format_predictions(ai_result, now)
        except (KeyError, TypeError, ValueError):
            logger.exception("AI service returned an invalid forecast")
            forecast_error = "Dự báo tạm thời không khả dụng."
    elif online and not light:
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
        "thresholds": AlertSetting.load().thresholds(),
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


# ---------------------------------------------------------------- Các trang giao diện
def _page(request, name, page, **extra):
    return render(request, f"monitor/{name}.html", {"page": page, "location": settings.LOCATION_NAME, **extra})


def overview(request):
    return _page(request, "overview", "overview", ranges=[(60, "1 giờ"), (360, "6 giờ"), (1440, "24 giờ")],
                 today=timezone.localtime().strftime("%d/%m/%Y"))


def forecast_page(request):
    return _page(request, "forecast", "forecast")


def suggestions(request):
    return _page(request, "suggestions", "suggestions")


def history(request):
    th = AlertSetting.load().thresholds()
    today = timezone.localdate()

    def day(name, default):
        try:
            return datetime.strptime(request.GET[name], "%Y-%m-%d").date()
        except (KeyError, ValueError):
            return default

    end_d = day("end", today)
    start_d = day("start", end_d - timedelta(days=1))
    if start_d > end_d:
        start_d, end_d = end_d, start_d
    step = int(request.GET["step"]) if request.GET.get("step") in {"5", "15", "60"} else 5
    status = request.GET.get("status") if request.GET.get("status") in {"normal", "warn"} else "all"
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(start_d, time.min))
    end = timezone.make_aware(datetime.combine(end_d + timedelta(days=1), time.min))

    buckets = {}
    for ts, t, h in Reading.objects.filter(created_at__gte=start, created_at__lt=end).values_list(
            "created_at", "temperature", "humidity"):
        b = buckets.setdefault(int(ts.timestamp() // (step * 60)), [0.0, 0.0, 0])
        b[0] += t; b[1] += h; b[2] += 1
    rows = []
    for key in sorted(buckets, reverse=True):
        t, h = buckets[key][0] / buckets[key][2], buckets[key][1] / buckets[key][2]
        warn = not (th["temp_low"] <= t <= th["temp_high"] and th["hum_low"] <= h <= th["hum_high"])
        if (status == "normal" and warn) or (status == "warn" and not warn):
            continue
        rows.append({"time": datetime.fromtimestamp(key * step * 60, tz), "temp": round(t, 1), "hum": round(h), "warn": warn})

    paginator = Paginator(rows, 8)
    page_obj = paginator.get_page(request.GET.get("page"))
    keep = request.GET.copy(); keep.pop("page", None)
    return _page(request, "history", "history", page_obj=page_obj, total=len(rows), qs=keep.urlencode(),
                 pages=paginator.get_elided_page_range(page_obj.number, on_each_side=1, on_ends=1),
                 start=start_d, end=end_d, step=step, status=status,
                 export_minutes=1440, now=timezone.localtime())


def settings_page(request):
    cfg = AlertSetting.load()
    error = saved = None
    if request.method == "POST":
        try:
            vals = {k: float(request.POST[k]) for k in ("temp_low", "temp_high", "hum_low", "hum_high")}
            if vals["temp_low"] >= vals["temp_high"] or vals["hum_low"] >= vals["hum_high"]:
                raise ValueError("Giá trị tối thiểu phải nhỏ hơn giá trị tối đa.")
            if not (-40 <= vals["temp_low"] and vals["temp_high"] <= 85 and 0 <= vals["hum_low"] and vals["hum_high"] <= 100):
                raise ValueError("Nhiệt độ cần trong khoảng -40–85°C và độ ẩm trong 0–100%.")
        except KeyError:
            error = "Vui lòng nhập đủ 4 ngưỡng."
        except ValueError as e:
            error = str(e) if "nhỏ hơn" in str(e) or "khoảng" in str(e) else "Ngưỡng phải là số."
        if not error:
            for k, v in vals.items():
                setattr(cfg, k, v)
            cfg.notify_alert = "notify_alert" in request.POST
            cfg.notify_ai = "notify_ai" in request.POST
            cfg.notify_email = "notify_email" in request.POST
            cfg.save()
            saved = True
    latest = Reading.objects.first()
    return _page(request, "settings", "settings", cfg=cfg, error=error, saved=saved, latest=latest,
                 device=latest.device if latest else "esp32-01", sensor=settings.SENSOR_TYPE)
