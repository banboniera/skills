"""Carrier scan stream adapter."""
from copy import deepcopy


def carrier_rows(items):
    row = {"code": "", "details": {"location": ""}}
    for code, location in items:
        row["code"] = code
        row["details"]["location"] = location
        yield row


def freeze_scan(row):
    return deepcopy(row)
