"""TimeWindow — query window for dashboard metrics (PRD §7.8)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum


class WindowKey(StrEnum):
    LAST_HOUR = "1h"
    LAST_24_HOURS = "24h"
    LAST_7_DAYS = "7d"


WINDOW_TO_DELTA: dict[WindowKey, timedelta] = {
    WindowKey.LAST_HOUR: timedelta(hours=1),
    WindowKey.LAST_24_HOURS: timedelta(hours=24),
    WindowKey.LAST_7_DAYS: timedelta(days=7),
}


def window_bounds(window: WindowKey, *, now: datetime | None = None) -> tuple[datetime, datetime]:
    """Return (since, until) for ``window`` relative to ``now`` (UTC)."""
    end = now or datetime.now(tz=UTC)
    start = end - WINDOW_TO_DELTA[window]
    return start, end
