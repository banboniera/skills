"""Planted bugs and mutants for each eval fixture. Each fix turns the shipped (buggy) model into correct code."""

# The fixture ships with three bugs; "correct code" fixes all of them, and each mutant below puts one back or breaks one behavior.
BUGGY_OPEN = "return self.filter(status=RepairOrder.Status.OPEN)"
FIXED_OPEN = "return self.exclude(status=RepairOrder.Status.CLOSED)"
BUGGY_PLATE_CLEAN = "    def save(self, *args, **kwargs):\n        \"\"\"Store plates trimmed"
FIXED_PLATE_CLEAN = "    def clean(self):\n        self.license_plate = self.license_plate.strip().upper()\n\n" + BUGGY_PLATE_CLEAN
BUGGY_NOTIFY = "        if self.status == self.Status.READY:\n"
FIXED_NOTIFY = '        if self.status == self.Status.READY and "status" in (kwargs.get("update_fields") or {"status"}):\n'
GARAGE_FIXES = [(BUGGY_OPEN, FIXED_OPEN), (BUGGY_PLATE_CLEAN, FIXED_PLATE_CLEAN), (BUGGY_NOTIFY, FIXED_NOTIFY)]
GARAGE_MUTANTS = [
    ("plate uppercase", "self.license_plate.strip().upper()\n        if (update_fields", "self.license_plate.strip()\n        if (update_fields"),
    ("plate trim", "self.license_plate.strip().upper()\n        if (update_fields", "self.license_plate.upper()\n        if (update_fields"),
    ("plate kept on partial save", 'kwargs["update_fields"] = {"license_plate", *update_fields}', "pass"),
    ("balance boundary at zero", 'MinValueValidator(Decimal("0.00"))', 'MinValueValidator(Decimal("0.01"))'),
    ("balance validator", 'validators=[MinValueValidator(Decimal("0.00"))],', "validators=[],"),
    ("closed order needs closed_at", "if self.status == self.Status.CLOSED and self.closed_at is None:", "if False:"),
    ("closed_at not in future", "if self.closed_at and self.closed_at > timezone.now():", "if False:"),
    ("vehicle from same workshop", "if self.vehicle_id and self.workshop_id and self.vehicle.workshop_id != self.workshop_id:", "if False:"),
    ("plate unique only among live vehicles", "                condition=Q(is_deleted=False),\n", ""),
    ("plate unique per workshop", 'models.UniqueConstraint(\n                fields=["workshop", "license_plate"],', 'models.UniqueConstraint(\n                fields=["id", "workshop", "license_plate"],'),
    ("vehicle without orders is removed", "if self.orders.exists():", "if True:"),
    ("vehicle with orders is kept", "if self.orders.exists():", "if False:"),
    ("soft delete records deleted_at", "            self.deleted_at = timezone.now()\n", ""),
    ("alive() hides deleted", "return self.filter(is_deleted=False)", "return self.all()"),
    ("queryset delete goes through instances", "count = 0\n        for vehicle in self:\n            deleted, _ = vehicle.delete()\n            count += deleted\n        return count, {self.model._meta.label: count}", "return super().delete()"),
    ("for_workshop() scopes", "return self.filter(workshop=workshop)", "return self.all()"),
    ("open() hides closed", FIXED_OPEN, "return self.all()"),
    ("bug: open() drops ready orders", FIXED_OPEN, BUGGY_OPEN),
    ("bug: full_clean() misses a duplicate typed differently", FIXED_PLATE_CLEAN, BUGGY_PLATE_CLEAN),
    ("bug: partial save without status still notifies", FIXED_NOTIFY, BUGGY_NOTIFY),
    ("notify only on becoming ready", "became_ready = previous != self.Status.READY", "became_ready = True"),
    ("notify only after commit", "transaction.on_commit(partial(tasks.notify_order_ready.delay, self.pk))", "tasks.notify_order_ready.delay(self.pk)"),
    ("notify at all", "transaction.on_commit(partial(tasks.notify_order_ready.delay, self.pk))", "pass"),
]

# Held-out fixture: none of its three bugs is named in the skill.
BUGGY_PURGE = "        count, _ = cls.objects.filter(is_active=False, anonymized=False).delete()\n        return count"
FIXED_PURGE = "        patients = list(cls.objects.filter(is_active=False, anonymized=False))\n        for patient in patients:\n            patient.delete()\n        return len(patients)"
BUGGY_UPCOMING = "return self.filter(starts_at__gt=timezone.now())"
FIXED_UPCOMING = "return self.filter(starts_at__gt=timezone.now(), cancelled=False)"
BUGGY_MAX = "if not self.MIN_MINUTES <= minutes < self.MAX_MINUTES:"
FIXED_MAX = "if not self.MIN_MINUTES <= minutes <= self.MAX_MINUTES:"
CLINIC_FIXES = [(BUGGY_PURGE, FIXED_PURGE), (BUGGY_UPCOMING, FIXED_UPCOMING), (BUGGY_MAX, FIXED_MAX)]
CLINIC_MUTANTS = [
    ("email lowercase", "self.email = self.email.strip().lower()", "self.email = self.email.strip()"),
    ("email trim", "self.email = self.email.strip().lower()", "self.email = self.email.lower()"),
    ("email unique ignoring case", 'models.UniqueConstraint(Lower("email"), name=', 'models.UniqueConstraint(fields=["email"], name='),
    ("email unique at all", 'constraints = [models.UniqueConstraint(Lower("email"), name="unique_patient_email_ci")]', "constraints = []"),
    ("delete blanks the name", '        self.name = "Removed patient"\n', ""),
    ("delete keeps the row", "        self.save()\n        return 0, {}", "        return super().delete(*args, **kwargs)"),
    ("delete deactivates", "        self.is_active = False\n", ""),
    ("purge only inactive patients", "cls.objects.filter(is_active=False, anonymized=False))", "cls.objects.filter(anonymized=False))"),
    ("bug: purge hard-deletes patients and their history", FIXED_PURGE, BUGGY_PURGE),
    ("upcoming() excludes past", FIXED_UPCOMING, "return self.filter(cancelled=False)"),
    ("bug: upcoming() includes cancelled", FIXED_UPCOMING, BUGGY_UPCOMING),
    ("for_patient() scopes", "return self.filter(patient=patient)", "return self.all()"),
    ("ends strictly after start", "condition=Q(ends_at__gt=F(\"starts_at\"))", "condition=Q(ends_at__gte=F(\"starts_at\"))"),
    ("minimum length inclusive", FIXED_MAX, "if not self.MIN_MINUTES < minutes <= self.MAX_MINUTES:"),
    ("bug: maximum length rejected", FIXED_MAX, BUGGY_MAX),
    ("length rule at all", FIXED_MAX, "if False:"),
    ("confirm only new bookings", "        if is_new:\n", "        if True:\n"),
    ("confirm only after commit", "transaction.on_commit(partial(reminders.send_booking_confirmation, self.pk))", "reminders.send_booking_confirmation(self.pk)"),
    ("confirm at all", "transaction.on_commit(partial(reminders.send_booking_confirmation, self.pk))", "pass"),
]

# Model change: the fixture is the clinic app with its bugs fixed and a good test suite; the task raises the limit to 180.
CHANGE_MUTANTS = [m for m in CLINIC_MUTANTS if not m[0].startswith("bug:") and m[1] != FIXED_MAX] + [
    ("new limit, not the old one", "MAX_MINUTES = 180", "MAX_MINUTES = 120"),
    ("new limit inclusive", FIXED_MAX, "if not self.MIN_MINUTES <= minutes < self.MAX_MINUTES:"),
    ("minimum unchanged and inclusive", FIXED_MAX, "if not self.MIN_MINUTES < minutes <= self.MAX_MINUTES:"),
    ("length rule at all", FIXED_MAX, "if False:"),
    ("purge keeps history", FIXED_PURGE, BUGGY_PURGE),
    ("upcoming() excludes cancelled", FIXED_UPCOMING, BUGGY_UPCOMING),
]

# Data migration: 0003's docstring promises a leading + kept and phone_digits already set kept; the shipped code does neither.
BUGGY_BACKFILL = '    for contact in Contact.objects.all():\n        contact.phone_digits = "".join(ch for ch in contact.phone if ch.isdigit())\n'
FIXED_BACKFILL = (
    '    for contact in Contact.objects.filter(phone_digits=""):\n'
    '        digits = "".join(ch for ch in contact.phone if ch.isdigit())\n'
    '        contact.phone_digits = "+" + digits if contact.phone.strip().startswith("+") else digits\n'
)
MIGRATE_MUTANTS = [
    ("bug: + dropped and existing values overwritten", FIXED_BACKFILL, BUGGY_BACKFILL),
    ("existing phone_digits kept", 'Contact.objects.filter(phone_digits="")', "Contact.objects.all()"),
    ("leading + kept", '"+" + digits if contact.phone.strip().startswith("+") else digits', "digits"),
    ("+ only when the number starts with it", 'contact.phone.strip().startswith("+")', '"+" in contact.phone'),
    ("digits only", "if ch.isdigit()", "if not ch.isspace()"),
    ("rows saved", '        contact.save(update_fields=["phone_digits"])\n', ""),
]
LATEST_SCHEMA_TEST = """from django.test import TransactionTestCase


class ZzzLatestSchemaTests(TransactionTestCase):
    def test_latest_schema_is_in_place(self):
        from crm.models import Contact

        Contact.objects.create(name="Later", phone="1", note="needs 0004")
        self.assertEqual(Contact.objects.count(), 1)
"""

SPECS = {
    "garage": {
        "fixture": "garage", "target": "shop/models.py",
        "app": "shop", "fixes": GARAGE_FIXES, "mutants": GARAGE_MUTANTS, "untouched": ["shop/models.py", "shop/tasks.py"], "base_class": "ShopTestCase",
        "reports": [
            ("Reports the open() bug", [r"open\(\)", r"ready|READY", r"(?i)bug|wrong|excludes|drops|misses|omits|incorrect|contradict"]),
            ("Reports the duplicate-plate validation bug", [r"full_clean|clean\(\)|validat", r"(?i)lower|case|typed|upper", r"(?i)IntegrityError|duplicate|unique"]),
            ("Reports the partial-save notification bug", [r"update_fields", r"(?i)notif"]),
        ],
    },
    "clinic": {
        "fixture": "clinic", "target": "clinic/models.py",
        "app": "clinic", "fixes": CLINIC_FIXES, "mutants": CLINIC_MUTANTS, "untouched": ["clinic/models.py", "clinic/reminders.py"], "base_class": None,
        "reports": [
            ("Reports the purge bug", [r"purge_inactive", r"(?i)hard|cascade|QuerySet\.delete|queryset delete|bypass|history"]),
            ("Reports the upcoming() bug", [r"upcoming", r"(?i)cancel"]),
            ("Reports the maximum-length bug", [r"120|MAX_MINUTES", r"(?i)inclusive|boundary|reject|exactly"]),
        ],
    },
    "change": {
        "fixture": "change", "target": "clinic/models.py", "app": "clinic",
        "fixes": [("MAX_MINUTES = 120", "MAX_MINUTES = 180")], "mutants": CHANGE_MUTANTS,
        "target_must_become_correct": True, "min_tests": 6, "stale_label": "No test still asserts the old limit",
        "reports": [("Reports the changed expectation", [r"test_length|121|181", r"(?i)120|old|updat|chang"])],
    },
    "migrate": {
        "fixture": "migrate", "target": "crm/migrations/0003_backfill_phone_digits.py", "app": "crm",
        "fixes": [(BUGGY_BACKFILL, FIXED_BACKFILL)], "mutants": MIGRATE_MUTANTS,
        "untouched": ["crm/migrations/0003_backfill_phone_digits.py", "crm/models.py"],
        "hidden_tests": {"test_zzz_latest_schema.py": LATEST_SCHEMA_TEST},
        "hidden_checks": [("Leaves the latest schema for later tests", "crm.tests.test_zzz_latest_schema.")],
        "reports": [
            ("Reports that the leading + is dropped", [r"\+|plus", r"(?i)drop|lost|strip|remov|missing|not kept|loses"]),
            ("Reports that existing values are overwritten", [r"(?i)overwrit|already set|existing|keep"]),
        ],
    },
}
