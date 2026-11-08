"""Tax region lookup."""

RATES = {"standard": "20", "reduced": "5", "exempt": "0"}

def region_rate(region: str) -> str:
    return RATES[region]
