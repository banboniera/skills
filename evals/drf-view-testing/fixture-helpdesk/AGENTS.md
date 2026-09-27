# Helpdesk

Django project with Django REST Framework, one app: `tickets`. Token authentication; routes in `helpdesksite/urls.py`.

- View tests live in `tickets/tests/views/`, one module per view module: `test_<module>.py`. Extend `tickets.tests.base.TicketsTestCase` and use its `setup_*` helpers.
- Run tests: `PYTHON manage.py test tickets` (or a single module, e.g. `tickets.tests.views.test_views`).
