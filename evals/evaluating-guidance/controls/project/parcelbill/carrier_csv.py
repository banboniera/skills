"""Carrier address-file parser."""
import csv
import io


def read_carrier_csv(text):
    return list(csv.DictReader(io.StringIO(text, newline="")))
