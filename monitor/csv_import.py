"""Đọc, kiểm tra và lưu tạm tệp CSV người dùng tải lên để chạy dự báo (không ghi vào bảng Reading)."""
import csv
import io
import json
import math
import re
import statistics
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

from django.utils import timezone

MAX_BYTES = 10 * 1024 * 1024
NEED_HOURS = 24                      # AI cần 24 giờ liên tục gần nhất
REQUIRED = ("thoi_gian", "nhiet_do", "do_am")
STORE = Path(tempfile.gettempdir()) / "climateai_csv"
TIME_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")


def _parse_time(text):
    for fmt in TIME_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def analyse(raw, name):
    """Trả về (info, errors). info=None khi tệp không đọc được; errors rỗng nghĩa là có thể chạy dự báo."""
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None, ["Tệp không phải mã hóa UTF-8."]
    reader = csv.reader(io.StringIO(text))
    cols = [c.strip().lower() for c in next(reader, [])]
    absent = [c for c in REQUIRED if c not in cols]
    if absent:
        return None, [f"Thiếu cột bắt buộc: {', '.join(absent)}."]
    idx = [cols.index(c) for c in REQUIRED]
    tz = timezone.get_current_timezone()
    seen, missing, skipped, dup, in_order, prev = {}, 0, 0, 0, True, None
    for row in reader:
        if not any(c.strip() for c in row):
            continue
        try:
            ts_s, t_s, h_s = (row[i].strip() for i in idx)
        except IndexError:
            missing += 1
            continue
        if not (ts_s and t_s and h_s):
            missing += 1
            continue
        ts = _parse_time(ts_s)
        try:
            t, h = float(t_s), float(h_s)
        except ValueError:
            t = h = float("nan")
        if ts is None or not (math.isfinite(t) and math.isfinite(h)) or not (-40 <= t <= 85 and 0 <= h <= 100):
            skipped += 1
            continue
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts, tz)
        if prev is not None and ts < prev:
            in_order = False
        prev = ts
        dup += ts in seen
        seen[ts] = (t, h)
    rows = [[int(ts.timestamp() * 1000), t, h] for ts, (t, h) in sorted(seen.items())]
    errors = []
    if not rows:
        return None, ["Không có dòng dữ liệu hợp lệ nào trong tệp."]
    hours = {r[0] // 3_600_000 for r in rows}
    last = max(hours)
    gaps = sum(1 for h in range(last - NEED_HOURS + 1, last + 1) if h not in hours)
    if gaps:
        errors.append(f"Cần đủ {NEED_HOURS} giờ liên tục tính đến bản ghi cuối, hiện đang thiếu {gaps} giờ.")
    step = round(statistics.median(b[0] - a[0] for a, b in zip(rows, rows[1:])) / 60000, 1) if len(rows) > 1 else None
    info = {"name": name, "size": len(raw), "count": len(rows), "start": rows[0][0], "end": rows[-1][0],
            "missing": missing, "skipped": skipped, "dup": dup, "reordered": not in_order, "step": step,
            "gap_hours": gaps, "rows": rows}
    return info, errors


def save(data, token=None):
    STORE.mkdir(exist_ok=True)
    cutoff = time.time() - 3600
    for old in STORE.glob("*.json"):
        if old.stat().st_mtime < cutoff:
            old.unlink(missing_ok=True)
    token = token or uuid.uuid4().hex
    (STORE / f"{token}.json").write_text(json.dumps(data), encoding="utf-8")
    return token


def load(token):
    if not token or not re.fullmatch(r"[0-9a-f]{32}", token):
        return None
    path = STORE / f"{token}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
