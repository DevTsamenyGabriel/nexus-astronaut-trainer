"""Shared mission settings. One place for the mission length so every screen agrees.
Default is the full 30-day mission; the 3-day quick run is for demos."""

FULL_DAYS = 30
QUICK_DAYS = 3
MISSION_DAYS = FULL_DAYS


def set_days(days: int) -> None:
    """Set the mission length before a mission starts."""
    global MISSION_DAYS
    MISSION_DAYS = max(2, int(days))


def is_quick() -> bool:
    return MISSION_DAYS != FULL_DAYS
