from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import text

from app.core.database_pool import db_pool


async def _ensure_pool():
    await db_pool.initialize()
    if not db_pool.session_factory:
        raise RuntimeError("Database pool not available")


async def _get_property_context(
    session,
    property_id: str,
    tenant_id: str,
) -> Tuple[str, Optional[datetime]]:
    result = await session.execute(
        text(
            """
            SELECT
                p.timezone AS property_timezone,
                MAX(r.check_in_date) AS latest_check_in
            FROM properties p
            LEFT JOIN reservations r
                ON r.property_id = p.id
               AND r.tenant_id = p.tenant_id
            WHERE p.id = :property_id
              AND p.tenant_id = :tenant_id
            GROUP BY p.timezone
            """
        ),
        {"property_id": property_id, "tenant_id": tenant_id},
    )
    row = result.fetchone()
    if not row:
        raise ValueError(f"Property {property_id} not found for tenant {tenant_id}")
    return row.property_timezone or "UTC", row.latest_check_in


def _resolve_reporting_period(
    latest_check_in: Optional[datetime],
    property_timezone: str,
    month: Optional[int],
    year: Optional[int],
) -> Tuple[int, int]:
    if month is not None and year is not None:
        return month, year

    if latest_check_in is None:
        now_local = datetime.now(ZoneInfo(property_timezone))
        return now_local.month, now_local.year

    latest_local = latest_check_in.astimezone(ZoneInfo(property_timezone))
    return latest_local.month, latest_local.year


async def calculate_monthly_revenue(
    property_id: str,
    tenant_id: str,
    month: Optional[int] = None,
    year: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Calculate revenue for a tenant-scoped property and reporting month.

    Revenue is bucketed by the property's local timezone so month boundaries
    match client financial reporting expectations.
    """
    await _ensure_pool()
    async with db_pool.get_session() as session:
        property_timezone, latest_check_in = await _get_property_context(
            session, property_id, tenant_id
        )
        report_month, report_year = _resolve_reporting_period(
            latest_check_in, property_timezone, month, year
        )

        result = await session.execute(
            text(
                """
                SELECT
                    COALESCE(SUM(r.total_amount), 0) AS total_revenue,
                    COUNT(r.id) AS reservation_count
                FROM reservations r
                JOIN properties p
                  ON p.id = r.property_id
                 AND p.tenant_id = r.tenant_id
                WHERE r.property_id = :property_id
                  AND r.tenant_id = :tenant_id
                  AND EXTRACT(MONTH FROM timezone(p.timezone, r.check_in_date)) = :month
                  AND EXTRACT(YEAR FROM timezone(p.timezone, r.check_in_date)) = :year
                """
            ),
            {
                "property_id": property_id,
                "tenant_id": tenant_id,
                "month": report_month,
                "year": report_year,
            },
        )
        row = result.fetchone()

    total_revenue = Decimal(str(row.total_revenue or "0"))
    return {
        "property_id": property_id,
        "tenant_id": tenant_id,
        "total": format(total_revenue, "f"),
        "currency": "USD",
        "count": int(row.reservation_count or 0),
        "month": report_month,
        "year": report_year,
        "timezone": property_timezone,
    }
