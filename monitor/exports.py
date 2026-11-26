"""Xuất số liệu ra CSV (để thống kê) và JSON (để AI đọc)."""
import csv
import io
import json
import statistics
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import Reading


def export_dir():
    return Path(getattr(settings, "EXPORT_DIR", Path(settings.BASE_DIR) / "exports"))


def fetch(start, end):
    return list(Reading.objects.filter(created_at__gte=start, created_at__lt=end).order_by("created_at"))


def base_name(start, end):
    s, e = timezone.localtime(start), timezone.localtime(end)
    return f"readings_{s:%Y%m%d_%H%M}_{e:%Y%m%d_%H%M}"


def csv_text(rows):
    """Cột: time, device, temperature, humidity. Giờ theo múi giờ địa phương."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["time", "device", "temperature", "humidity"])
    for r in rows:
        w.writerow([timezone.localtime(r.created_at).strftime("%Y-%m-%d %H:%M:%S"),
                    r.device, r.temperature, r.humidity])
    return buf.getvalue()


def _stats(values):
    if not values:
        return None
    return {"min": min(values), "max": max(values), "mean": round(statistics.fmean(values), 2),
            "first": values[0], "last": values[-1]}


def json_text(rows, start, end):
    """Metadata và thống kê tóm tắt ở đầu, mỗi lượt đo một dòng để AI dễ đọc."""
    meta = {
        "location": settings.LOCATION_NAME,
        "sensor": getattr(settings, "SENSOR_TYPE", "unknown"),
        "timezone": settings.TIME_ZONE,
        "units": {"temperature": "°C", "humidity": "%"},
        "period": {"start": timezone.localtime(start).isoformat(timespec="seconds"),
                   "end": timezone.localtime(end).isoformat(timespec="seconds")},
        "count": len(rows),
        "summary": {"temperature": _stats([r.temperature for r in rows]),
                    "humidity": _stats([r.humidity for r in rows])},
    }
    readings = [
        {"time": timezone.localtime(r.created_at).isoformat(timespec="seconds"),
         "device": r.device, "temperature": r.temperature, "humidity": r.humidity}
        for r in rows
    ]
    head = json.dumps(meta, ensure_ascii=False, indent=2)
    lines = ",\n".join("    " + json.dumps(x, ensure_ascii=False) for x in readings)
    return head[:-2] + ',\n  "readings": [\n' + lines + "\n  ]\n}\n"


def export_range(start, end, out_dir=None):
    """Ghi 2 file .csv và .json cho khoảng [start, end). Trả về None nếu không có số liệu."""
    rows = fetch(start, end)
    if not rows:
        return None
    out = Path(out_dir) if out_dir else export_dir()
    out.mkdir(parents=True, exist_ok=True)
    name = base_name(start, end)
    csv_path, json_path = out / f"{name}.csv", out / f"{name}.json"
    csv_path.write_text(csv_text(rows), encoding="utf-8-sig")  # BOM để Excel đọc đúng
    json_path.write_text(json_text(rows, start, end), encoding="utf-8")
    return csv_path, json_path, len(rows)


def export_previous_hour(now=None):
    """Khi sang giờ mới, tự xuất giờ tròn vừa qua (vd 14:00–15:00) nếu chưa có file."""
    if not getattr(settings, "EXPORT_AUTO_HOURLY", True):
        return None
    now = timezone.localtime(now or timezone.now())
    end = now.replace(minute=0, second=0, microsecond=0)
    start = end - timedelta(hours=1)
    name = base_name(start, end)
    if (export_dir() / f"{name}.csv").exists() and (export_dir() / f"{name}.json").exists():
        return None
    return export_range(start, end)
