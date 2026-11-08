"""Cart pricing helpers."""

def coupon_allowed(code: str) -> bool:
    return code.startswith("SAVE-") and len(code) > 5
