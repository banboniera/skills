---
name: drf-serializer-testing
description: Write unit tests for Django REST Framework serializers — validation, save behavior, representation, context-driven querysets, and nested writes. Use whenever the user asks to test, cover, or verify a DRF serializer (ModelSerializer, Serializer, ListSerializer), mentions serializer validation errors, validated_data, to_representation, or asks for tests for files named serializers.py or tests under tests/serializers/, even if they just say "add tests" for code that turns out to be a serializer.
---

# DRF Serializer Testing

Test serializer contract only — validation errors, normalized/saved state, representation. Never DRF internals: plain `CharField` rejecting `None` is DRF's job. Test what serializer adds: custom validators, field config, querysets, save logic, output shape.

## Workflow

1. Read serializer + everything it touches: fields, `validate_<field>()`, `validate()`, `create()`/`update()`, `to_representation()`, `SerializerMethodField`s, queryset callables, models. Trace context use (`self.context["request"]`, user, company, language). Never test unread code.
2. Find project serializer test base + neighboring tests before raw `TestCase` boilerplate. Reuse its fixtures + assertion helpers, never hand-roll shared models. Project-specific conventions (bases, fixtures, run command): read `references/` — see Bundled resources.
3. Coverage gaps unknown? Run `scripts/untested_serializers.py <project-src-dir>` — lists serializer classes no test references.
4. Classify serializer, pick coverage from table: writable (form/create/update), read-only (list/detail/select), nested/collection. `scripts/coverage_map.py <serializers.py> [Class]` prints per-class checklist of owned fields/validators/hooks mapped to required tests — supplements step 1, never replaces it: `!`-marked lines flag statically invisible fields (`__all__`, Meta-derived, `get_fields()`); step 1's reading is authoritative.
5. Write tests: one behavior per test, explicit setup, exact assertions. Mirror test path convention (`<app>/tests/serializers/test_<name>.py`).
6. Run tests for touched module only, not whole suite.

**Batch coverage** (many untested serializers, subagents available): shard by MODULE, one subagent per module — never per class (siblings share fixtures/base). Each subagent brief: this SKILL.md path + target module + output test path; workers write tests only — syntax check (`ast.parse`) at most; never run suite/linters mid-batch. Orchestrator merges, then runs new test modules **serially** at the end — concurrent `manage.py test` invocations collide on the shared `test_<dbname>` database. No subagents: work through gap list module by module, same rule.

## What to cover

| Area | Do |
|------|-----|
| **Validation** | Every writable serializer: ≥1 valid + ≥1 invalid payload. Assert `serializer.errors` **by key and shape** — never stop at `assertFalse(serializer.is_valid())`. Cover every custom `validate_<field>()` and `validate()` branch. Every field serializer **owns** (declared or configured — incl. `ChoiceField` choices, min/max, format): valid + boundary/invalid value. Assert coerced/normalized `validated_data`. Validation raising `PermissionDenied` (or other DRF exception): assert exact class + message. Invalid input: assert **DB unchanged**. |
| **Save** | Writable `ModelSerializer` IS the write contract: cover `create` + full `update` even without custom methods. **`partial=True`** separately: assert changed AND unchanged fields. Parent-supplied relations: `serializer.save(user=…)` kwargs — test that path directly. Save touching related rows, M2M, detail models, generated values: assert **every** side effect after `save()` from persisted state (`refresh_from_db`), never only returned instance. |
| **Context & querysets** | Context-driven behavior (user, company, language, tenant): set context, assert outcome. Writable relations with dynamic/filtered querysets: in-scope IDs pass, out-of-scope IDs **fail at validation** — tenant-isolation boundary; missing test here = security gap. Nested serializers receiving context: exercise filtering **through parent**. |
| **Read / output** | Assert **exact** key set of `.data`, never presence of few keys — extra keys leak data silently. Match `SerializerMethodField`, `ReadOnlyField`, translated labels, computed totals, flattened relations to known fixtures. `write_only` keys **absent** from `.data`. Custom `to_representation()`: test path directly. |
| **Query budget** | DRF never optimizes querysets — `SerializerMethodField`/nested/related access hides N+1. List/detail serializer touching relations: wrap `.data` in `assertNumQueries(N)`; prefetched instance: assert `assertNumQueries(0)`. Budget = representation contract. |
| **Nested & collections** | Writable nested payloads: valid + invalid; nested errors on **parent** with correct key structure. Updates mixing existing child `pk` + new rows: assert created, updated, kept, removed. Reject unavailable related objects at validation — never rely on post-save DB errors. `many=True`: `ListSerializer` supports multiple **create** only, never multiple update unless custom `ListSerializer.update`; list-level `allow_empty`/`max_length`: test boundaries when serializer sets them. |
| **Constraints** | Uniqueness/scope conflicts: **pre-create** conflicting row, then validate. DRF 3.16+ auto-generates validators from `Meta.constraints` `UniqueConstraint` (nullable + conditional included) — expect serializer-level error; assert `IntegrityError` only when contract intentionally defers to DB. Never duplicate pure model tests unless serializer changes validation/save contract. |

## Core patterns

Instantiate serializer directly — no view, no HTTP client. Views get own tests; client here adds auth/routing noise, hides which layer broke.

Prefer project test-base helpers over hand-rolled assertions when the base provides them (error-key asserts, partial-update diffs, exact-key checks) — sharper failures, consistent with neighboring tests. Examples below use plain `unittest` asserts: portable everywhere.

**Valid path — normalization + persisted state:**

```python
def test_create_normalizes_and_persists(self):
    serializer = PartFormSerializer(data=self._payload(), context=self.context)

    self.assertTrue(serializer.is_valid(), serializer.errors)  # errors as msg → readable failures
    self.assertEqual(serializer.validated_data["name"], self.part_name)
    part = serializer.save()
    part.refresh_from_db()
    self.assertEqual(part.code, "PART-001")
    self.assertEqual(set(part.mechanics.values_list("pk", flat=True)), {self.mechanic.pk})
```

**Invalid path — error key, message, clean DB:**

```python
def test_rejects_out_of_scope_mechanic(self):
    serializer = PartFormSerializer(
        data=self._payload(mechanics=[self.other_company_mechanic.pk]),
        context=self.context,
    )

    self.assertFalse(serializer.is_valid())
    self.assertEqual(set(serializer.errors), {"mechanics"})
    self.assertIn("Invalid pk", str(serializer.errors["mechanics"][0]))
    self.assertEqual(Part.objects.count(), 0)
```

**Owned fields — every configured field gets boundary/invalid test:**

```python
def test_rejects_unknown_role(self):
    serializer = AssignmentFormSerializer(
        data=self._payload(role="not-a-role"), context=self.context
    )

    self.assertFalse(serializer.is_valid())
    self.assertEqual(set(serializer.errors), {"role"})
    self.assertIn("not a valid choice", str(serializer.errors["role"][0]))
```

**Boundary testing — one valid payload, break one field per test:**

```python
def _payload(self, **overrides):
    return {"name": self.part_name.pk, "code": "PART-001", "quantity": "2.0", **overrides}
```

Payload-builder method per serializer: override IS the scenario.

**Partial update — changed vs unchanged, separate from full update:**

```python
def test_partial_update_changes_only_code(self):
    part = self._create_part()
    serializer = PartPartialUpdateSerializer(part, data={"code": "NEW"}, partial=True, context=self.context)

    self.assertTrue(serializer.is_valid(), serializer.errors)
    serializer.save()
    part.refresh_from_db()
    self.assertEqual(part.code, "NEW")
    self.assertEqual(part.quantity, Decimal("2.0"))  # untouched field survived
```

**Read serializer — exact keys against known fixtures:**

```python
def test_list_representation(self):
    part = self._create_part()
    data = PartListSerializer(part, context=self.context).data

    self.assertEqual(set(data.keys()), {"id", "name", "code", "quantity", "status"})
    self.assertEqual(data["name"], "Brake Pad")  # translated via context language
```

**Query budget — representation cost is contract when serializer touches relations:**

```python
def test_detail_representation_query_budget(self):
    vehicle = Vehicle.objects.prefetch_related("labels").get(pk=self.vehicle.pk)

    with self.assertNumQueries(0):
        data = VehicleDetailSerializer(vehicle, context=self.context).data

    self.assertEqual(data["labels"], [self.vehicle_label.pk])
```

**Context — pass whenever behavior depends on it.** Request-like object enough (project base often provides a builder); full `APIRequestFactory` only when serializer reads real request attributes:

```python
def setUp(self):
    request = SimpleNamespace(user=self.manager_user, auth=SimpleNamespace(company=self.company))
    self.context = {"request": request}
```

## Anti-patterns

- `assertFalse(serializer.is_valid())` without error inspection — passes for wrong error.
- `is_valid(raise_exception=True)` in tests — loses `serializer.errors` structure.
- Testing inherited DRF field mechanics (`IntegerField` rejecting `"abc"` with no custom config).
- Asserting only instance returned by `save()` — generated/derived values may differ in DB; `refresh_from_db()` first.
- Per-test fixtures every test needs — use `setUpTestData` (once per class, isolated per test).
- Shared mutable state between tests; each test builds own payload.
- Re-reading `serializer.data` after mutation — `.data` cached on first access; re-instantiate serializer to observe changes.

## Version notes

- `setUpTestData` attrs deep-copied per test since Django 3.2; Django 6.0 **requires** deepcopyable — mutating fixture in test safe + isolated; never stash non-copyable objects (open files, connections) on class.
- DRF 3.16+ generates uniqueness validators from `Meta.constraints` `UniqueConstraint` (nullable + conditional) — most conflicts surface in `serializer.errors`, not `IntegrityError`.
- Queryset comparisons: `assertQuerySetEqual` (capital S) with real objects; string/`repr` comparison gone (Django 5.1+).
- DRF 3.17/3.18: no serializer contract change — Django 6 + Python 3.14 support, security fixes.

## Bundled resources

- `references/huggingcar.md` — HuggingCar api project: stack pins, test bases, helper list, fixtures, paths, run command. Read when working in that repo.
- `scripts/untested_serializers.py` — print serializer classes unreferenced by any test. Usage: `python scripts/untested_serializers.py /path/to/project/src`.
- `scripts/coverage_map.py` — per-class checklist of owned fields/validators/hooks mapped to required tests. Usage: `python scripts/coverage_map.py path/to/serializers.py [ClassName]`.

## Quick verify (before finishing)

Context present when needed. Valid + invalid paths; error structure asserted; every custom validator branch + owned field covered; normalization asserted when relevant. Writable serializer: create, full update, partial update (field diff), `save(**kwargs)` path when parent supplies relations; rejected writes leave DB clean; post-save persisted state + related/M2M side effects asserted. Scoped relation IDs: in-scope passes, out-of-scope fails. Uniqueness conflicts pre-created. Read output: exact keys, computed/translated fields, no `write_only` keys; query budget asserted when representation touches relations. Nested writes + nested error structure when feature exists.

## References

- https://www.django-rest-framework.org/api-guide/serializers/
- https://www.django-rest-framework.org/api-guide/validators/
- https://www.vintasoftware.com/blog/how-i-test-my-drf-serializers
- https://testdriven.io/blog/drf-serializers/
