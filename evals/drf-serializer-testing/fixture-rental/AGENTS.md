# Rentals

Django project with Django REST Framework, one app: `rentals`.

- Serializer tests live in `rentals/tests/serializers/`, one module per serializer module: `test_<module>.py`. Extend `rentals.tests.base.RentalsTestCase` and use its `setup_*` helpers and `serializer_context()`.
- Run tests: `PYTHON manage.py test rentals` (or a single module, e.g. `rentals.tests.serializers.test_serializers`).
