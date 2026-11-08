"""Customer-facing tracking labels."""

CARRIERS = {"north": "North Parcel", "local": "Local Courier"}

def carrier_name(code: str) -> str:
    return CARRIERS.get(code, code)
