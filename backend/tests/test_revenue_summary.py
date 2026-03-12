import unittest
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.api.v1.dashboard import get_dashboard_summary
from app.models.auth import AuthenticatedUser
from app.services.reservations import _resolve_reporting_period


class RevenueSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_dashboard_summary_preserves_subcent_precision_and_period(self):
        user = AuthenticatedUser(
            id="user-sunset",
            email="sunset@propertyflow.com",
            permissions=[],
            cities=[],
            is_admin=False,
            tenant_id="tenant-a",
        )

        mocked_summary = {
            "property_id": "prop-001",
            "tenant_id": "tenant-a",
            "total": "2250.000",
            "currency": "USD",
            "count": 4,
            "month": 3,
            "year": 2024,
            "timezone": "Europe/Paris",
        }

        with patch(
            "app.api.v1.dashboard.get_revenue_summary",
            new=AsyncMock(return_value=mocked_summary),
        ):
            response = await get_dashboard_summary("prop-001", current_user=user)

        self.assertEqual(response["total_revenue"], "2250.000")
        self.assertEqual(response["reservations_count"], 4)
        self.assertEqual(response["month"], 3)
        self.assertEqual(response["year"], 2024)
        self.assertEqual(response["timezone"], "Europe/Paris")

    def test_reporting_period_uses_property_timezone_boundary(self):
        # 2024-02-29 23:30 UTC is 2024-03-01 00:30 in Paris.
        from datetime import datetime, timezone

        report_month, report_year = _resolve_reporting_period(
            datetime(2024, 2, 29, 23, 30, tzinfo=timezone.utc),
            "Europe/Paris",
            month=None,
            year=None,
        )

        self.assertEqual((report_month, report_year), (3, 2024))

    async def test_dashboard_summary_returns_not_found_for_cross_tenant_property(self):
        user = AuthenticatedUser(
            id="user-ocean",
            email="ocean@propertyflow.com",
            permissions=[],
            cities=[],
            is_admin=False,
            tenant_id="tenant-b",
        )

        with patch(
            "app.api.v1.dashboard.get_revenue_summary",
            new=AsyncMock(side_effect=ValueError("Property prop-002 not found for tenant tenant-b")),
        ):
            with self.assertRaises(HTTPException) as ctx:
                await get_dashboard_summary("prop-002", current_user=user)

        self.assertEqual(ctx.exception.status_code, 404)
        self.assertIn("tenant-b", ctx.exception.detail)


if __name__ == "__main__":
    unittest.main()
