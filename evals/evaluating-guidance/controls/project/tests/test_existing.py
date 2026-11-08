"""Visible regression coverage; monetary conventions intentionally are not here."""
import unittest
from parcelbill.contacts import display_name
from parcelbill.invoices import line_codes
from parcelbill.pricing import coupon_allowed
from parcelbill.refunds import covered_days
from parcelbill.shipping import billable_weight
from parcelbill.subscriptions import extra_seats
from parcelbill.tax import region_rate
from parcelbill.telemetry import capture, record
from parcelbill.tracking import carrier_name


class ExistingBehavior(unittest.TestCase):
    def test_helpers(self):
        self.assertTrue(coupon_allowed("SAVE-JUNE"))
        self.assertFalse(coupon_allowed("SAVE-"))
        self.assertEqual(region_rate("standard"), "20")
        self.assertEqual(covered_days(5, 8), 3)
        self.assertEqual(covered_days(8, 5), 0)
        self.assertEqual(billable_weight("1.2", "3.4"), "3.4")
        self.assertEqual(extra_seats(1, 3), 0)
        self.assertEqual(line_codes([{"code": "BOX"}]), ["BOX"])
        self.assertEqual(carrier_name("north"), "North Parcel")
        self.assertEqual(display_name({"name": " ", "email": "a@example.test"}), "a@example.test")

    def test_event_capture_is_scoped(self):
        record("outside", "discarded")
        with capture() as outer:
            record("sample", "outer")
            with capture() as inner:
                record("sample", "inner")
        self.assertEqual(outer, [{"kind": "sample", "subject": "outer"}])
        self.assertEqual(inner, [{"kind": "sample", "subject": "inner"}])
