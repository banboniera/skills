"""Parcel weight classification."""
from decimal import Decimal

def billable_weight(actual: str, dimensional: str) -> str:
    return str(max(Decimal(actual), Decimal(dimensional)))
