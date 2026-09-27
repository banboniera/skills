/** Order page (/orders/<id>): GET /api/orders/<id>/, shown as a heading "Order <plate>" and the order's details. */
import { api } from '../api.js'
import { escape } from '../ui.js'

export const mount = async (root, { params: [id] }) => {
  const order = await api('GET', `/orders/${id}/`)
  root.innerHTML = `
    <p><a href="/orders">Back to orders</a></p>
    <h1>Order ${escape(order.plate)}</h1>
    <dl>
      <dt>Customer</dt><dd>${escape(order.customer)}</dd>
      <dt>Status</dt><dd>${escape(order.status)}</dd>
      <dt>Due</dt><dd>${escape(order.due_date)}</dd>
    </dl>`
}
