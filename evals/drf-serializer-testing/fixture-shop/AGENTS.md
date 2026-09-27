# Shop

Django project with Django REST Framework, one app: `orders`.

- Serializer tests live in `orders/tests/serializers/`, one module per serializer module: `test_<module>.py`. Extend `orders.tests.base.OrdersTestCase` and use its `setup_*` helpers and `serializer_context()`.
- Run tests: `PYTHON manage.py test orders` (or a single module, e.g. `orders.tests.serializers.test_serializers`).
