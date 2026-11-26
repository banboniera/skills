# Workshop CRM backend

Backend for a CRM used by Polish car workshops: customers, their cars, service
orders, invoices. Workshop staff use the staff app; a workshop's customers can
see their own cars and orders in a mobile customer app.

- Postgres schema: `migrations/0001_crm.sql`. Not deployed yet: no backward
  compatibility is needed, and migrations may be rewritten.
- A customer app user gets access to a workshop's customer record only by
  accepting an SMS invitation (`customer_access`). A matching phone number
  grants nothing.
- A walk-in order (`service_orders.customer_id IS NULL`) has no customer
  record; staff only create the order and take payment.
