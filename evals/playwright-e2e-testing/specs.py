"""Planted bugs and mutants for each eval fixture. Each fix turns the shipped (buggy) page into correct code."""

ORDERS = "src/pages/orders.js"

# Bug 1: the delete buttons are shown to every signed-in user, viewers included.
BUGGY_DELETE_GATE = "${session.user ? `<button"
FIXED_DELETE_GATE = "${isManager ? `<button"
# Bug 2: "Next page" drops the status filter.
BUGGY_NEXT = "next.addEventListener('click', () => load({ page: state.page + 1, plate: state.plate }))"
FIXED_NEXT = "next.addEventListener('click', () => load({ page: state.page + 1, plate: state.plate, status: state.status }))"
# Bug 3: the due date is parsed as UTC midnight and compared with the current instant, so an order due today is overdue.
BUGGY_OVERDUE = "order.status === 'open' && new Date(order.due_date) < new Date()"
FIXED_OVERDUE = "order.status === 'open' && order.due_date < today()"
WORKSHOP_FIXES = [(BUGGY_DELETE_GATE, FIXED_DELETE_GATE), (BUGGY_NEXT, FIXED_NEXT), (BUGGY_OVERDUE, FIXED_OVERDUE)]

RELOAD = "const reload = () => load({ page: 1, plate: state.plate, status: state.status })"
CATCH_LOAD = """      list.innerHTML = '<div role="alert">Could not load orders <button type="button" id="retry">Retry</button></div>'
      list.querySelector('#retry').addEventListener('click', () => load(query))"""
DELETE_TRY = """      await api('DELETE', `/orders/${id}/`)
      button.closest('tr').remove()"""
WORKSHOP_MUTANTS = [
    ("page_size not sent", "query: { ...query, page_size: PAGE_SIZE }", "query: { ...query }"),
    ("search sent as `search`", RELOAD, "const reload = () => load({ page: 1, search: state.plate, status: state.status })"),
    ("search not uppercased", "state.plate = event.target.plate.value.trim().toUpperCase()", "state.plate = event.target.plate.value.trim()"),
    ("search keeps the current page", "state.plate = event.target.plate.value.trim().toUpperCase()\n    reload()", "state.plate = event.target.plate.value.trim().toUpperCase()\n    load({ page: state.page, plate: state.plate, status: state.status })"),
    ("status filter ignored", "state.status = event.target.value", "state.status = ''"),
    ("no empty state", "list.innerHTML = '<p>No orders match</p>'", "list.innerHTML = ''"),
    ("load failure shows the empty state", CATCH_LOAD, "      renderRows([])"),
    ("retry does nothing", "addEventListener('click', () => load(query))", "addEventListener('click', () => {})"),
    ("retry drops the filters", "addEventListener('click', () => load(query))", "addEventListener('click', () => load({ page: 1 }))"),
    ("no loading state", "list.innerHTML = '<p>Loading orders…</p>'", "list.innerHTML = ''"),
    ("previous page enabled on page 1", "prev.disabled = state.page <= 1", "prev.disabled = false"),
    ("next page enabled on the last page", "next.disabled = state.page >= pages", "next.disabled = false"),
    ("page count rounds down", "Math.ceil(data.count / PAGE_SIZE)", "Math.floor(data.count / PAGE_SIZE)"),
    ("previous page drops the search", "load({ page: state.page - 1, plate: state.plate, status: state.status })", "load({ page: state.page - 1 })"),
    ("next page drops the search", FIXED_NEXT, "next.addEventListener('click', () => load({ page: state.page + 1, status: state.status }))"),
    ("next page drops the status", FIXED_NEXT, BUGGY_NEXT),
    ("done orders overdue", FIXED_OVERDUE, "order.due_date < today()"),
    ("due today is overdue", FIXED_OVERDUE, "order.status === 'open' && order.due_date <= today()"),
    ("plate link goes nowhere", "navigate(link.getAttribute('href'))", "navigate('/orders')"),
    ("viewer sees New order", "${isManager ? '<button type=\"button\" id=\"new-order\">", "${session.user ? '<button type=\"button\" id=\"new-order\">"),
    ("viewer sees delete", FIXED_DELETE_GATE, BUGGY_DELETE_GATE),
    ("delete without confirmation", "    if (!(await confirmDialog(`Delete order ${plate}?`, 'Delete'))) return\n", ""),
    ("cancel still deletes", "if (!(await confirmDialog(`Delete order ${plate}?`, 'Delete'))) return", "await confirmDialog(`Delete order ${plate}?`, 'Delete')"),
    ("delete sends the plate as id", "api('DELETE', `/orders/${id}/`)", "api('DELETE', `/orders/${plate}/`)"),
    ("row removed before the API answers", DELETE_TRY, "      button.closest('tr').remove()\n      await api('DELETE', `/orders/${id}/`)"),
    ("failed delete not announced", "      toast('Could not delete order')\n", ""),
    ("customer not required", "    if (!body.customer) errors.customer = 'Enter the customer'\n", ""),
    ("plate format not checked", "    else if (!PLATE.test(body.plate)) errors.plate = 'Use 2–8 letters or digits'\n", ""),
    ("due date not required", "    if (!body.due_date) errors.due_date = 'Pick the due date'\n", ""),
    ("plate sent as typed", "await api('POST', '/orders/', { body })", "await api('POST', '/orders/', { body: { ...body, plate: form.plate.value } })"),
    ("due date not sent", "await api('POST', '/orders/', { body })", "await api('POST', '/orders/', { body: { customer: body.customer, plate: body.plate } })"),
    ("Create not disabled while saving", "    submit.disabled = true\n", ""),
    ("dialog stays open after create", "      close()\n      toast('Order created')", "      toast('Order created')"),
    ("list not reloaded after create", "      toast('Order created')\n      reload()", "      toast('Order created')"),
    ("server field errors hidden", "failure.status === 400 && failure.body) showErrors(failure.body)", "failure.status === 400 && failure.body) showErrors({})"),
    ("dialog closes on a rejected create", "      submit.disabled = false\n    }\n  })", "      submit.disabled = false\n      close()\n    }\n  })"),
]

BOOKINGS = "src/pages/bookings.js"

# Bug 1: members see the cancel button on everyone's bookings, not only their own.
BUGGY_CANCEL_GATE = "const canCancel = (booking) => isAdmin || session.user.role === 'member'"
FIXED_CANCEL_GATE = "const canCancel = (booking) => isAdmin || (canBook && booking.owner.id === session.user.id)"
# Bug 2: a booking that ends when it starts passes validation.
BUGGY_END = "if (body.ends_at < body.starts_at) errors.end"
FIXED_END = "if (body.ends_at <= body.starts_at) errors.end"
# Bug 3: times are shown in UTC instead of the user's local time.
BUGGY_CLOCK = "return `${pad(date.getUTCHours())}:${pad(date.getUTCMinutes())}`"
FIXED_CLOCK = "return `${pad(date.getHours())}:${pad(date.getMinutes())}`"
ROOMS_FIXES = [(BUGGY_CANCEL_GATE, FIXED_CANCEL_GATE), (BUGGY_END, FIXED_END), (BUGGY_CLOCK, FIXED_CLOCK)]

ROOMS_MUTANTS = [
    ("date not sent", "query: { date: state.day, owner:", "query: { owner:"),
    ("opens on the UTC date", "const state = { day: formatDay(new Date()), mine: false }", "const state = { day: new Date().toISOString().slice(0, 10), mine: false }"),
    ("previous day moves forward", "state.day = shiftDay(state.day, -1)", "state.day = shiftDay(state.day, 1)"),
    ("next day skips a day", "state.day = shiftDay(state.day, 1)", "state.day = shiftDay(state.day, 2)"),
    ("heading not updated", "root.querySelector('h1').textContent = `Bookings for ${state.day}`", "root.querySelector('h1').textContent ||= `Bookings for ${state.day}`"),
    ("times shown in UTC", FIXED_CLOCK, BUGGY_CLOCK),
    ("not sorted by start", "const sorted = [...bookings].sort((a, b) => a.starts_at.localeCompare(b.starts_at))", "const sorted = [...bookings]"),
    ("no empty state", "list.innerHTML = '<p>No bookings on this day</p>'", "list.innerHTML = ''"),
    ("load failure shows the empty state", "list.innerHTML = '<p role=\"alert\">Could not load bookings</p>'", "list.innerHTML = '<p>No bookings on this day</p>'"),
    ("only mine not sent", "owner: state.mine ? 'me' : undefined", "owner: undefined"),
    ("only mine dropped when changing day", "    state.day = shiftDay(state.day, 1)\n    load()", "    state.day = shiftDay(state.day, 1)\n    state.mine = false\n    load()"),
    ("guest can book", "const canBook = session.user.role !== 'guest'", "const canBook = true"),
    ("members cancel others' bookings", FIXED_CANCEL_GATE, BUGGY_CANCEL_GATE),
    ("admins cannot cancel others' bookings", FIXED_CANCEL_GATE, "const canCancel = (booking) => canBook && booking.owner.id === session.user.id"),
    ("owners cannot cancel their bookings", FIXED_CANCEL_GATE, "const canCancel = (booking) => isAdmin"),
    ("guests cancel their own bookings", FIXED_CANCEL_GATE, "const canCancel = (booking) => isAdmin || booking.owner.id === session.user.id"),
    ("cancelled bookings keep the button", "${booking.status !== 'cancelled' && canCancel(booking) ?", "${canCancel(booking) ?"),
    ("cancel without confirmation", "    if (!(await confirmDialog(`Cancel ${booking.title}?`, 'Cancel booking', 'Keep'))) return\n", ""),
    ("keep still cancels", "if (!(await confirmDialog(`Cancel ${booking.title}?`, 'Cancel booking', 'Keep'))) return", "await confirmDialog(`Cancel ${booking.title}?`, 'Cancel booking', 'Keep')"),
    ("cancel sent as DELETE", "await api('POST', `/bookings/${booking.id}/cancel/`)", "await api('DELETE', `/bookings/${booking.id}/`)"),
    ("cancelled booking not marked", "      booking.status = 'cancelled'\n", ""),
    ("title not required", "    if (!body.title) errors.title = 'Enter a title'\n", ""),
    ("title not trimmed", "title: form.title.value.trim(),", "title: form.title.value,"),
    ("end equal to start allowed", FIXED_END, BUGGY_END),
    ("end before start allowed", "    if (body.ends_at <= body.starts_at) errors.end = 'End after the start'\n", ""),
    ("times sent as local", "starts_at: new Date(`${day}T${form.start.value}`).toISOString(),", "starts_at: `${day}T${form.start.value}:00`,"),
    ("room sent as its name", "room: Number(form.room.value),", "room: form.room.selectedOptions[0].textContent,"),
    ("dialog stays open after booking", "      close()\n      toast('Room booked')", "      toast('Room booked')"),
    ("no booked announcement", "      toast('Room booked')\n", ""),
    ("day not reloaded after booking", "      toast('Room booked')\n      reload()", "      toast('Room booked')"),
    ("conflict closes the dialog", "      showErrors({ form: failure instanceof ApiError && failure.status === 409", "      close()\n      showErrors({ form: failure instanceof ApiError && failure.status === 409"),
    ("conflict message missing", "'That room is already booked then'", "'Could not book the room, try again'"),
]

# Change task: search matches customers too, so the page sends `search` (trimmed, as typed) from a box named "Search orders".
CHANGE_FIXES = [
    ('<input type="search" name="plate" placeholder="Search by plate" aria-label="Search by plate" />', '<input type="search" name="search" placeholder="Search orders" aria-label="Search orders" />'),
    ("const state = { page: 1, plate: '', status: '', count: 0 }", "const state = { page: 1, search: '', status: '', count: 0 }"),
    (RELOAD, "const reload = () => load({ page: 1, search: state.search, status: state.status })"),
    ("    state.plate = event.target.plate.value.trim().toUpperCase()\n", "    state.search = event.target.search.value.trim()\n"),
    ("load({ page: state.page - 1, plate: state.plate, status: state.status })", "load({ page: state.page - 1, search: state.search, status: state.status })"),
    (FIXED_NEXT, "next.addEventListener('click', () => load({ page: state.page + 1, search: state.search, status: state.status }))"),
]
CHANGE_MUTANTS = [
    ("search still sent as plate", "const reload = () => load({ page: 1, search: state.search, status: state.status })", "const reload = () => load({ page: 1, plate: state.search, status: state.status })"),
    ("search uppercased", "state.search = event.target.search.value.trim()", "state.search = event.target.search.value.trim().toUpperCase()"),
    ("search not trimmed", "state.search = event.target.search.value.trim()", "state.search = event.target.search.value"),
    ("search keeps the current page", "    state.search = event.target.search.value.trim()\n    reload()", "    state.search = event.target.search.value.trim()\n    load({ page: state.page, search: state.search, status: state.status })"),
    ("next page sends plate", "load({ page: state.page + 1, search: state.search, status: state.status })", "load({ page: state.page + 1, plate: state.search, status: state.status })"),
    ("previous page drops the search", "load({ page: state.page - 1, search: state.search, status: state.status })", "load({ page: state.page - 1, status: state.status })"),
    ("box still named Search by plate", 'placeholder="Search orders" aria-label="Search orders"', 'placeholder="Search by plate" aria-label="Search by plate"'),
    ("status change drops the search", "    state.status = event.target.value\n    reload()", "    state.status = event.target.value\n    load({ page: 1, status: state.status })"),
    ("viewer sees delete", FIXED_DELETE_GATE, BUGGY_DELETE_GATE),
    ("due today is overdue", FIXED_OVERDUE, "order.status === 'open' && order.due_date <= today()"),
    ("plate sent as typed", "await api('POST', '/orders/', { body })", "await api('POST', '/orders/', { body: { ...body, plate: form.plate.value } })"),
    ("cancel still deletes", "if (!(await confirmDialog(`Delete order ${plate}?`, 'Delete'))) return", "await confirmDialog(`Delete order ${plate}?`, 'Delete')"),
    ("retry does nothing", "addEventListener('click', () => load(query))", "addEventListener('click', () => {})"),
    ("no loading state", "list.innerHTML = '<p>Loading orders…</p>'", "list.innerHTML = ''"),
]
CHANGE_FINAL = """import { expect, test } from '@playwright/test'

import { openPage, type ApiHandler, type RecordedRequest } from './helpers'

const lists = (requests: RecordedRequest[]) => requests.filter((r) => r.method === 'GET' && r.path === '/orders/')
const api: ApiHandler = async (route, request) => {
  if (request.path !== '/orders/') return false
  await route.fulfill({ json: { count: 45, results: [{ id: Number(request.query.page), customer: 'Jan Kowalski', plate: `P${request.query.page}X`, status: 'open', due_date: '2099-01-01' }] } })
  return true
}

test('search sends the text as typed, trimmed, from page 1, and paging keeps it', async ({ page }) => {
  const requests = await openPage(page, '/orders', { api: [api] })
  await expect(page.getByText('Page 1 of 3')).toBeVisible()
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(page.getByText('Page 2 of 3')).toBeVisible()
  const box = page.getByRole('searchbox', { name: 'Search orders' })
  await box.fill('  Kowal ')
  await box.press('Enter')
  await expect(page.getByText('Page 1 of 3')).toBeVisible()
  expect(lists(requests).at(-1)?.query).toEqual({ page: '1', search: 'Kowal', page_size: '20' })
  await page.getByLabel('Status').selectOption('open')
  await expect.poll(() => lists(requests).at(-1)?.query).toEqual({ page: '1', search: 'Kowal', status: 'open', page_size: '20' })
  await expect(page.getByText('Page 1 of 3')).toBeVisible()
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect(page.getByText('Page 2 of 3')).toBeVisible()
  expect(lists(requests).at(-1)?.query).toEqual({ page: '2', search: 'Kowal', status: 'open', page_size: '20' })
  await page.getByRole('button', { name: 'Previous page' }).click()
  await expect(page.getByText('Page 1 of 3')).toBeVisible()
  expect(lists(requests).at(-1)?.query).toEqual({ page: '1', search: 'Kowal', status: 'open', page_size: '20' })
  await box.fill('')
  await box.press('Enter')
  await expect.poll(() => lists(requests).at(-1)?.query).toEqual({ page: '1', status: 'open', page_size: '20' })
})
"""

SPECS = {
    "workshop": {
        "fixture": "workshop",
        "target": ORDERS,
        "fixes": WORKSHOP_FIXES,
        "mutants": WORKSHOP_MUTANTS,
        "untouched": [ORDERS, "e2e/helpers.ts"],
        "reports": [
            ("Reports that viewers see delete buttons", [r"(?i)viewer", r"(?i)delete"]),
            ("Reports that next page drops the status", [r"(?i)next", r"(?i)status"]),
            ("Reports that orders due today show as overdue", [r"(?i)overdue", r"(?i)today|timezone|UTC"]),
        ],
    },
    "rooms": {
        "fixture": "rooms",
        "target": BOOKINGS,
        "fixes": ROOMS_FIXES,
        "mutants": ROOMS_MUTANTS,
        "untouched": [BOOKINGS, "e2e/helpers.ts"],
        "reports": [
            ("Reports that members can cancel others' bookings", [r"(?i)member", r"(?i)cancel", r"(?i)other|anyone|every|not (their|own)|someone else"]),
            ("Reports that a booking may end when it starts", [r"(?i)end", r"(?i)equal|same|zero|<="]),
            ("Reports that times show in UTC", [r"(?i)UTC", r"(?i)local|time ?zone"]),
        ],
    },
    "change": {
        "fixture": "change",
        "target": ORDERS,
        "fixes": CHANGE_FIXES,
        "mutants": CHANGE_MUTANTS,
        "change": True,
        "final_tests": {"final-search.spec.ts": CHANGE_FINAL},
        "min_tests": 20,
        "stale_label": "No test asserts the old search",
        "reports": [],
    },
}
