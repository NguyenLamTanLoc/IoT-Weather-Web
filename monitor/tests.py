from django.test import TestCase, override_settings

from monitor.models import Reading


@override_settings(INGEST_API_KEY="test-api-key")
class ApiIngestTests(TestCase):
    def test_accepts_x_api_key_header(self):
        response = self.client.post(
            "/api/ingest/",
            data={"temperature": 28.5, "humidity": 71.2, "device": "esp32-test"},
            content_type="application/json",
            headers={"X-API-Key": "test-api-key"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Reading.objects.filter(device="esp32-test").exists())

    def test_rejects_missing_api_key(self):
        response = self.client.post(
            "/api/ingest/",
            data={"temperature": 28.5, "humidity": 71.2},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 401)

# ---------------------------------------------------------------- Mật khẩu Cài đặt + nhập CSV
import json as _json
from datetime import timedelta as _td
from unittest import mock as _mock

from django.test import TestCase as _TestCase, override_settings as _override
from django.utils import timezone as _tz

from . import csv_import
from .models import AlertSetting as _AS


def _csv(hours=30, step_min=5, header="thoi_gian,nhiet_do,do_am"):
    end = _tz.localtime().replace(minute=0, second=0, microsecond=0)
    lines = [header]
    for i in range(hours * 60 // step_min, -1, -1):
        t = end - _td(minutes=i * step_min)
        lines.append(f"{t:%Y-%m-%d %H:%M:%S},{28 + (i % 7) * 0.1:.1f},{65 - i % 5}")
    return "\n".join(lines).encode("utf-8")


PLAIN_STATIC = {"default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
                "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}}  # không cần collectstatic khi test


@_override(ADMIN_PASSWORD="mat-khau-test", STORAGES=PLAIN_STATIC)
class AdminGateTests(_TestCase):
    def test_settings_locked_until_login(self):
        r = self.client.get("/settings/")
        self.assertContains(r, "Yêu cầu mật khẩu quản trị")
        self.assertNotContains(r, "Ngưỡng cảnh báo")

    def test_post_without_login_changes_nothing(self):
        self.client.post("/settings/", {"temp_low": 1, "temp_high": 2, "hum_low": 3, "hum_high": 4})
        self.assertNotEqual(_AS.load().temp_high, 2)

    def test_empty_and_wrong_password(self):
        r = self.client.post("/settings/login/", {"password": ""})
        self.assertContains(r, "Vui lòng nhập mật khẩu quản trị để tiếp tục.")
        r = self.client.post("/settings/login/", {"password": "sai"})
        self.assertContains(r, "Mật khẩu không đúng.")
        self.assertNotContains(self.client.get("/settings/"), "Ngưỡng cảnh báo")

    def test_correct_password_unlocks_then_locks(self):
        r = self.client.post("/settings/login/", {"password": "mat-khau-test"})
        self.assertRedirects(r, "/settings/")
        self.assertContains(self.client.get("/settings/"), "Ngưỡng cảnh báo")
        self.client.post("/settings/logout/")
        self.assertNotContains(self.client.get("/settings/"), "Ngưỡng cảnh báo")

    def test_lockout_after_five_failures(self):
        from django.core.cache import cache
        cache.clear()
        for _ in range(5):
            self.client.post("/settings/login/", {"password": "sai"})
        r = self.client.post("/settings/login/", {"password": "mat-khau-test"})
        self.assertContains(r, "quá nhiều lần")

    @_override(ADMIN_PASSWORD="", STORAGES=PLAIN_STATIC)
    def test_no_password_configured_stays_locked(self):
        r = self.client.post("/settings/login/", {"password": "bat-ky"})
        self.assertContains(r, "ADMIN_PASSWORD")
        self.assertNotContains(self.client.get("/settings/"), "Ngưỡng cảnh báo")


@_override(STORAGES=PLAIN_STATIC)
class CsvImportTests(_TestCase):
    def test_valid_file(self):
        info, errors = csv_import.analyse(_csv(), "a.csv")
        self.assertEqual(errors, [])
        self.assertEqual(info["step"], 5)

    def test_missing_column(self):
        info, errors = csv_import.analyse(_csv(header="thoi_gian,nhiet_do,x"), "a.csv")
        self.assertIsNone(info)
        self.assertIn("do_am", errors[0])

    def test_less_than_24_hours(self):
        info, errors = csv_import.analyse(_csv(hours=10), "a.csv")
        self.assertTrue(errors)
        self.assertGreater(info["gap_hours"], 0)

    def test_bad_rows_are_skipped_and_counted(self):
        raw = _csv() + b"\nkhong-phai-gio,30,50\n2026-01-01 00:00:00,200,50\n2026-01-01 00:05:00,,50"
        info, errors = csv_import.analyse(raw, "a.csv")
        self.assertEqual((info["skipped"], info["missing"]), (2, 1))

    def test_upload_flow_and_forecast(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        r = self.client.post("/forecast/csv/", {"file": SimpleUploadedFile("du_lieu.csv", _csv())})
        self.assertRedirects(r, "/forecast/csv/check/")
        self.assertContains(self.client.get("/forecast/csv/check/"), "Dữ liệu hợp lệ")
        now = _tz.now()
        fake = {"predictions": [{"time": (now + _td(hours=h)).isoformat(), "temperature": 30 + h, "humidity": 60}
                                for h in range(1, 7)]}
        with _mock.patch("monitor.views._csv_call_ai", return_value=fake):
            r = self.client.post("/forecast/csv/run/")
        self.assertRedirects(r, "/forecast/csv/result/")
        page = self.client.get("/forecast/csv/result/")
        self.assertContains(page, "Dự báo từ tệp CSV")
        self.assertContains(page, 'id="csv-data"')
        self.assertEqual(Reading.objects.count(), 0)   # CSV không ghi vào dữ liệu cảm biến

    def test_rejects_non_csv_and_empty(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.assertContains(self.client.post("/forecast/csv/", {"file": SimpleUploadedFile("a.txt", b"x")}), "định dạng .csv")
        self.assertContains(self.client.post("/forecast/csv/", {}), "chọn một tệp CSV")

    def test_pages_without_session_redirect(self):
        for u in ("/forecast/csv/check/", "/forecast/csv/result/"):
            self.assertRedirects(self.client.get(u), "/forecast/csv/")
