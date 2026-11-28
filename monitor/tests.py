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