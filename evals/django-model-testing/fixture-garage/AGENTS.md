# Garage

Django project, one app: `shop`.

- Tests live in `shop/tests/`, one module per model: `test_<model>.py`. Extend `shop.tests.base.ShopTestCase` and use its `setup_*` helpers.
- Run tests: `PYTHON manage.py test shop` (or a single module, e.g. `shop.tests.test_workshop`).
