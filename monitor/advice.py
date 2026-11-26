"""Gợi ý theo luật đơn giản dựa trên số liệu hiện tại và dự báo. Có thể thay bằng gợi ý do AI sinh ra."""
from django.conf import settings


def build_advice(latest, forecast):
    th = settings.THRESHOLDS
    if latest is None:
        return [{"level": "warn", "title": "Chưa có số liệu",
                 "detail": "Cảm biến chưa gửi dữ liệu nào. Kiểm tra nguồn điện và kết nối Wi-Fi của ESP32."}]

    t_next = max([latest.temperature] + [p["temperature"] for p in forecast])
    t_min = min([latest.temperature] + [p["temperature"] for p in forecast])
    h_next = max([latest.humidity] + [p["humidity"] for p in forecast])
    h_min = min([latest.humidity] + [p["humidity"] for p in forecast])
    out = []

    if t_next >= th["temp_high"]:
        now_hot = latest.temperature >= th["temp_high"]
        out.append({"level": "alert" if now_hot else "warn",
                    "title": "Nhiệt độ cao" if now_hot else "Nhiệt độ sắp vượt ngưỡng",
                    "detail": f"Có thể đạt {t_next:.1f}°C. Bật quạt hoặc mở cửa thông gió, che nắng nếu có thể."})
    elif t_min <= th["temp_low"]:
        out.append({"level": "warn", "title": "Nhiệt độ thấp",
                    "detail": f"Có thể xuống {t_min:.1f}°C. Đóng bớt cửa thông gió hoặc bật sưởi."})

    if h_next >= th["hum_high"]:
        out.append({"level": "warn", "title": "Độ ẩm cao",
                    "detail": f"Có thể đạt {h_next:.0f}%. Tăng thông gió để tránh đọng nước và nấm mốc."})
    elif h_min <= th["hum_low"]:
        out.append({"level": "warn", "title": "Không khí khô",
                    "detail": f"Độ ẩm có thể xuống {h_min:.0f}%. Phun sương hoặc tưới thêm."})

    if not out:
        out.append({"level": "ok", "title": "Điều kiện ổn định",
                    "detail": "Nhiệt độ và độ ẩm dự kiến nằm trong ngưỡng cho phép trong 6 giờ tới."})
    return out
