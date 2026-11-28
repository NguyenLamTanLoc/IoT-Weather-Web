from django.db import models
from django.utils import timezone


class Reading(models.Model):
    """Một lần đo từ cảm biến (ESP32 gửi lên server)."""

    device = models.CharField("Thiết bị", max_length=40, default="esp32-01")
    temperature = models.FloatField("Nhiệt độ (°C)")
    humidity = models.FloatField("Độ ẩm (%)")
    created_at = models.DateTimeField("Thời điểm đo", default=timezone.now, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Số liệu đo"
        verbose_name_plural = "Số liệu đo"

    def __str__(self):
        return f"{self.device} {self.created_at:%H:%M:%S} {self.temperature}°C {self.humidity}%"
