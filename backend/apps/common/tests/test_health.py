from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase

HEALTH_URL = "/api/v1/health/"


class HealthEndpointTests(APITestCase):
    def test_is_reachable_without_authentication(self):
        response = self.client.get(HEALTH_URL)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_reports_each_dependency(self):
        response = self.client.get(HEALTH_URL)

        self.assertEqual(response.data["status"], "ok")
        self.assertEqual(response.data["checks"], {"database": "ok", "cache": "ok"})

    def test_reports_degraded_when_a_dependency_fails(self):
        with mock.patch("apps.common.views.check_cache", return_value="error"):
            response = self.client.get(HEALTH_URL)

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data["status"], "degraded")
        self.assertEqual(response.data["checks"]["cache"], "error")

    def test_dependency_failure_does_not_leak_details(self):
        with mock.patch(
            "apps.common.views.connection.cursor",
            side_effect=Exception("connection to server at 10.0.0.5 failed: password auth"),
        ):
            response = self.client.get(HEALTH_URL)

        self.assertEqual(response.data["checks"]["database"], "error")
        self.assertNotIn("10.0.0.5", str(response.data))
        self.assertNotIn("password", str(response.data))
