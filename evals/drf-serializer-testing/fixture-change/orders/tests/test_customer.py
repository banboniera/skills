from orders.tests.base import OrdersTestCase


class CustomerTests(OrdersTestCase):
    def test_customer_belongs_to_company(self):
        company = self.setup_company()
        customer = self.setup_customer(company)
        self.assertEqual(list(company.customers.all()), [customer])
