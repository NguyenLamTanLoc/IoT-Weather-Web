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


class AlertSetting(models.Model):
    """Cài đặt ngưỡng cảnh báo và thông báo (chỉ có 1 dòng, sửa ở trang Cài đặt)."""

    temp_low = models.FloatField("Nhiệt độ tối thiểu (°C)", default=18)
    temp_high = models.FloatField("Nhiệt độ tối đa (°C)", default=32)
    hum_low = models.FloatField("Độ ẩm tối thiểu (%)", default=40)
    hum_high = models.FloatField("Độ ẩm tối đa (%)", default=85)
    notify_alert = models.BooleanField("Cảnh báo vượt ngưỡng", default=True)
    notify_ai = models.BooleanField("Gợi ý từ AI", default=True)
    notify_email = models.BooleanField("Báo cáo qua email", default=False)

    @classmethod
    def load(cls):
        from django.conf import settings
        th = settings.THRESHOLDS
        obj, _ = cls.objects.get_or_create(pk=1, defaults={
            "temp_low": th["temp_low"], "temp_high": th["temp_high"],
            "hum_low": th["hum_low"], "hum_high": th["hum_high"]})
        return obj

    def thresholds(self):
        return {"temp_low": self.temp_low, "temp_high": self.temp_high,
                "hum_low": self.hum_low, "hum_high": self.hum_high}
