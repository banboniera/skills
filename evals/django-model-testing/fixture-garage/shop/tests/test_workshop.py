from shop.tests.base import ShopTestCase


class WorkshopTests(ShopTestCase):
    def test_workshop_has_no_open_orders_at_first(self):
        workshop = self.setup_workshop()
        self.assertEqual(workshop.open_order_count(), 0)
