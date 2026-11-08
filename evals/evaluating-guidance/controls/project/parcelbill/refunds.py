"""Service-period accounting."""

def covered_days(start_day: int, end_day: int) -> int:
    return max(0, end_day - start_day)
