# Testing data migrations

A data migration (`RunPython`) runs once against the real rows in production, and a mistake in it is hard to undo. It works on historical models (`apps.get_model()`), the model as it was at that point in the migration history, so its test has to put the database in that historical state, insert rows with the historical model, run the migration, and read the result back the same way.

## What to test

- Every kind of row production holds: the typical case, and the edges the transform has to survive, such as empty or null values, unexpected casing or whitespace, and duplicates a later constraint will reject.
- Rows already in the target state, such as rows new code wrote before the migration ran, and rows the migration must not touch at all: test what the migration does to each on purpose.
- The reverse function, when the migration has one. With `RunPython.noop`, rolling back leaves the data as it is; with no reverse function, the migration cannot be rolled back at all (Django raises `IrreversibleError`). Say which applies rather than testing it.
- A constraint added right after the data migration: migrate through it in the test, so the test proves the migrated data satisfies it.

Also read the migration for two problems a test will not show. It must get models through `apps.get_model()`, never import them from `models.py`, or it breaks once the model changes later. And on a large table it should stream rows (`iterator()`, batched `bulk_update()`) rather than load them all at once.

## How

```python
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class BackfillEmailDomainTests(TransactionTestCase):
    migrate_from = [("crm", "0002_customer_email_domain")]
    migrate_to = [("crm", "0003_backfill_email_domain")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.migrate_from)
        OldCustomer = executor.loader.project_state(self.migrate_from).apps.get_model("crm", "Customer")
        self.mixed_case = OldCustomer.objects.create(email="ann@Example.COM").pk
        self.already_set = OldCustomer.objects.create(email="bob@example.com", email_domain="kept.example").pk

        executor = MigrationExecutor(connection)  # a fresh executor sees the new migration state
        executor.migrate(self.migrate_to)
        self.Customer = executor.loader.project_state(self.migrate_to).apps.get_model("crm", "Customer")

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())  # back to the latest schema for later tests

    def test_backfills_domain_in_lowercase(self):
        self.assertEqual(self.Customer.objects.get(pk=self.mixed_case).email_domain, "example.com")

    def test_leaves_existing_domain_alone(self):
        self.assertEqual(self.Customer.objects.get(pk=self.already_set).email_domain, "kept.example")
```

- Use `TransactionTestCase`. Migrating inside `TestCase`'s transaction fails on SQLite (its schema editor refuses to run inside a transaction while foreign key checks are on), and it would hide how the migration behaves in a real transaction elsewhere.
- Create input rows with the model from `migrate_from`, and read results with the model from `migrate_to`. The current model can have fields the old table does not have yet.
- Create a new `MigrationExecutor` after each `migrate()`: its loader holds the migration state from when it was built.
- Migrate back to the latest schema in `tearDown()`. Otherwise every later `TransactionTestCase` runs against the old tables.
- Each test migrates the database, so these tests are slow: keep them few by putting several kinds of row into one test's setup and assertions, and tag them the way the project tags slow tests. If the project already uses django-test-migrations, use its `MigratorTestCase`, which does the same with less code.
