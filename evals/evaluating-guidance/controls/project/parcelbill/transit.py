"""Carrier timestamps and zone selection."""
from datetime import timezone
from zoneinfo import ZoneInfo


def carrier_zone():
    return ZoneInfo("Europe/Warsaw")
