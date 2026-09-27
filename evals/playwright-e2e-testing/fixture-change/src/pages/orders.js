/**
 * Orders page (/orders).
 *
 * - Lists the workshop's orders with GET /api/orders/?page=<n>&page_size=20, in the order the API returns them
 *   ({"count": <total>, "results": [{id, customer, plate, status: "open" | "done", due_date: "YYYY-MM-DD"}]}).
 *   While the request is in flight the table shows "Loading orders…". An empty page shows "No orders match".
 *   A failed request shows the alert "Could not load orders" with a "Retry" button that requests the same page again.
 * - "Search by plate" (submitted with Enter) sends `plate=<value>`, trimmed and uppercased, and goes back to page 1;
 *   an empty search drops the parameter.
 * - The "Status" select sends `status=open` or `status=done`; "All statuses" drops the parameter. Changing it goes back to page 1.
 * - "Next page" and "Previous page" move through the pages (`page`), keeping the search and the status.
 *   "Previous page" is disabled on page 1 and "Next page" on the last page (from `count`). The footer reads "Page <n> of <total>".
 * - An open order whose due date is before today (the user's local date) shows an "Overdue" badge. An order due today
 *   is not overdue, and a done order never is.
 * - Clicking an order's plate opens /orders/<id>.
 * - Managers see "New order", which opens the "New order" dialog with Customer, Plate, and Due date, all required;
 *   the plate must be 2–8 letters or digits once trimmed and uppercased. Invalid fields show an error under the field
 *   and nothing is sent. "Create" sends POST /api/orders/ with {customer, plate, due_date} (customer trimmed, plate
 *   trimmed and uppercased) and stays disabled until the API answers. On 201 the dialog closes, "Order created" is
 *   announced, and the list reloads. On 400 the API's field errors ({"plate": ["..."]}) show under their fields and
 *   the dialog stays open.
 * - Managers see a "Delete <plate>" button on each order. It asks "Delete order <plate>?"; "Delete" sends
 *   DELETE /api/orders/<id>/ and removes the row once the API answers 204, and "Cancel" sends nothing. When the delete
 *   fails the row stays and "Could not delete order" is announced.
 * - Viewers can list, search, filter, and page through orders, but see neither "New order" nor the delete buttons.
 */
import { api, ApiError } from '../api.js'
import { confirmDialog, escape, toast } from '../ui.js'

const PAGE_SIZE = 20
const PLATE = /^[A-Z0-9]{2,8}$/

const today = () => {
  const now = new Date()
  const pad = (n) => String(n).padStart(2, '0')
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`
}

const isOverdue = (order) => order.status === 'open' && order.due_date < today()

export const mount = async (root, { session, navigate }) => {
  const isManager = session.user.role === 'manager'
  const state = { page: 1, plate: '', status: '', count: 0 }

  root.innerHTML = `
    <h1>Orders</h1>
    <div class="toolbar">
      <form role="search" id="search">
        <input type="search" name="plate" placeholder="Search by plate" aria-label="Search by plate" />
      </form>
      <label>Status
        <select name="status">
          <option value="">All statuses</option>
          <option value="open">Open</option>
          <option value="done">Done</option>
        </select>
      </label>
      ${isManager ? '<button type="button" id="new-order">New order</button>' : ''}
    </div>
    <div id="list"></div>
    <nav aria-label="Pagination">
      <button type="button" id="prev">Previous page</button>
      <span id="page-label"></span>
      <button type="button" id="next">Next page</button>
    </nav>`

  const list = root.querySelector('#list')
  const prev = root.querySelector('#prev')
  const next = root.querySelector('#next')

  const renderRows = (orders) => {
    if (orders.length === 0) {
      list.innerHTML = '<p>No orders match</p>'
      return
    }
    list.innerHTML = `
      <table>
        <thead><tr><th>Plate</th><th>Customer</th><th>Status</th><th>Due</th><th></th></tr></thead>
        <tbody>
          ${orders
            .map(
              (order) => `
            <tr data-id="${order.id}">
              <td><a href="/orders/${order.id}">${escape(order.plate)}</a></td>
              <td>${escape(order.customer)}</td>
              <td>${order.status === 'done' ? 'Done' : 'Open'}</td>
              <td>${escape(order.due_date)} ${isOverdue(order) ? '<span class="badge">Overdue</span>' : ''}</td>
              <td>${isManager ? `<button type="button" data-delete="${order.id}" data-plate="${escape(order.plate)}">Delete ${escape(order.plate)}</button>` : ''}</td>
            </tr>`,
            )
            .join('')}
        </tbody>
      </table>`
  }

  const load = async (query) => {
    list.innerHTML = '<p>Loading orders…</p>'
    prev.disabled = next.disabled = true
    try {
      const data = await api('GET', '/orders/', { query: { ...query, page_size: PAGE_SIZE } })
      state.page = query.page
      state.count = data.count
      renderRows(data.results)
      const pages = Math.max(1, Math.ceil(data.count / PAGE_SIZE))
      root.querySelector('#page-label').textContent = `Page ${state.page} of ${pages}`
      prev.disabled = state.page <= 1
      next.disabled = state.page >= pages
    } catch {
      list.innerHTML = '<div role="alert">Could not load orders <button type="button" id="retry">Retry</button></div>'
      list.querySelector('#retry').addEventListener('click', () => load(query))
    }
  }

  const reload = () => load({ page: 1, plate: state.plate, status: state.status })

  root.querySelector('#search').addEventListener('submit', (event) => {
    event.preventDefault()
    state.plate = event.target.plate.value.trim().toUpperCase()
    reload()
  })
  root.querySelector('select[name=status]').addEventListener('change', (event) => {
    state.status = event.target.value
    reload()
  })
  prev.addEventListener('click', () => load({ page: state.page - 1, plate: state.plate, status: state.status }))
  next.addEventListener('click', () => load({ page: state.page + 1, plate: state.plate, status: state.status }))

  list.addEventListener('click', async (event) => {
    const link = event.target.closest('a[href^="/orders/"]')
    if (link) {
      event.preventDefault()
      navigate(link.getAttribute('href'))
      return
    }
    const button = event.target.closest('button[data-delete]')
    if (!button) return
    const { delete: id, plate } = button.dataset
    if (!(await confirmDialog(`Delete order ${plate}?`, 'Delete'))) return
    try {
      await api('DELETE', `/orders/${id}/`)
      button.closest('tr').remove()
    } catch {
      toast('Could not delete order')
    }
  })

  if (isManager) {
    root.querySelector('#new-order').addEventListener('click', () => openNewOrder(reload))
  }

  await reload()
}

const openNewOrder = (reload) => {
  const dialog = document.createElement('dialog')
  dialog.setAttribute('aria-labelledby', 'new-order-title')
  dialog.innerHTML = `
    <h2 id="new-order-title">New order</h2>
    <form novalidate>
      <p><label>Customer <input name="customer" /></label><span class="field-error" data-error="customer"></span></p>
      <p><label>Plate <input name="plate" /></label><span class="field-error" data-error="plate"></span></p>
      <p><label>Due date <input name="due_date" type="date" min="${today()}" /></label><span class="field-error" data-error="due_date"></span></p>
      <button type="button" data-cancel>Cancel</button>
      <button type="submit">Create</button>
    </form>`
  document.body.append(dialog)
  const form = dialog.querySelector('form')
  const submit = form.querySelector('button[type=submit]')
  const close = () => {
    dialog.close()
    dialog.remove()
  }
  const showErrors = (errors) => {
    for (const slot of form.querySelectorAll('[data-error]')) {
      const message = errors[slot.dataset.error]
      slot.textContent = message ? [message].flat().join(' ') : ''
    }
  }
  form.querySelector('[data-cancel]').addEventListener('click', close)
  form.addEventListener('submit', async (event) => {
    event.preventDefault()
    const body = {
      customer: form.customer.value.trim(),
      plate: form.plate.value.trim().toUpperCase(),
      due_date: form.due_date.value,
    }
    const errors = {}
    if (!body.customer) errors.customer = 'Enter the customer'
    if (!body.plate) errors.plate = 'Enter the plate'
    else if (!PLATE.test(body.plate)) errors.plate = 'Use 2–8 letters or digits'
    if (!body.due_date) errors.due_date = 'Pick the due date'
    showErrors(errors)
    if (Object.keys(errors).length) return
    submit.disabled = true
    try {
      await api('POST', '/orders/', { body })
      close()
      toast('Order created')
      reload()
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 400 && failure.body) showErrors(failure.body)
      else showErrors({ customer: 'Could not create the order, try again' })
      submit.disabled = false
    }
  })
  dialog.showModal()
}
