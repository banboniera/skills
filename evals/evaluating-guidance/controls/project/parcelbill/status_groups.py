"""Status run adapter for already sorted event feeds."""
from itertools import groupby


def status_runs(events):
    return groupby(events, key=lambda event: event["status"])
