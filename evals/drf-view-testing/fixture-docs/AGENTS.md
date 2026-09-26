# Docs

Django project with Django REST Framework, one app: `documents`. Token authentication; routes in `docsite/urls.py`.

- View tests live in `documents/tests/views/`, one module per view module: `test_<module>.py`. Extend `documents.tests.base.DocumentsTestCase` and use its `setup_*` helpers.
- Run tests: `PYTHON manage.py test documents` (or a single module, e.g. `documents.tests.views.test_views`).
