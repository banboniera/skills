"""Team-seat allowances."""

def extra_seats(seats: int, included: int) -> int:
    return max(0, seats - included)
