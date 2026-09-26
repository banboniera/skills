import { expect, test, type Page } from '@playwright/test'

import { openPage, reply, type ApiHandler, type RecordedRequest, type Role } from './helpers'

const order = (id: number, plate: string, extra: Partial<Order> = {}): Order => ({
  id,
  customer: `Customer ${id}`,
  plate,
  status: 'open',
  due_date: '2026-04-01',
  ...extra,
})
type Order = { id: number; customer: string; plate: string; status: 'open' | 'done'; due_date: string }

/** GET /orders/ answered by `pick(query)`; everything else falls through. */
const ordersApi =
  (pick: (query: Record<string, string>) => { count: number; results: Order[] }): ApiHandler =>
  async (route, request) => {
    if (request.method !== 'GET' || request.path !== '/orders/') return false
    await route.fulfill({ json: pick(request.query) })
    return true
  }

const page1 = { count: 2, results: [order(1, 'AB123'), order(2, 'CD456')] }
const listRequests = (requests: RecordedRequest[]) => requests.filter((r) => r.method === 'GET' && r.path === '/orders/')

const openOrders = (page: Page, api: ApiHandler[] = [ordersApi(() => page1)], role: Role = 'manager') =>
  openPage(page, '/orders', { role, api })

const rows = (page: Page) => page.getByRole('row').filter({ has: page.getByRole('cell') })

test.describe('list', () => {
  test('shows the first page of orders', async ({ page }) => {
    const requests = await openOrders(page)
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByRole('row', { name: /AB123 Customer 1 Open/ })).toBeVisible()
    await expect(page.getByText('Page 1 of 1')).toBeVisible()
    expect(listRequests(requests)).toEqual([expect.objectContaining({ query: { page: '1', page_size: '20' } })])
  })

  test('shows a loading state until the list arrives', async ({ page }) => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    await openOrders(page, [
      async (route, request) => {
        if (request.path !== '/orders/') return false
        await gate
        await route.fulfill({ json: page1 })
        return true
      },
    ])
    await expect(page.getByText('Loading orders…')).toBeVisible()
    release()
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByText('Loading orders…')).toBeHidden()
  })

  test('shows the empty state', async ({ page }) => {
    await openOrders(page, [ordersApi(() => ({ count: 0, results: [] }))])
    await expect(page.getByText('No orders match')).toBeVisible()
    await expect(page.getByRole('table')).toHaveCount(0)
  })

  test('a failed load offers a retry of the same query', async ({ page }) => {
    let fail = false
    const requests = await openOrders(page, [
      async (route, request) => {
        if (request.path !== '/orders/') return false
        if (fail) await route.fulfill({ status: 500, json: {} })
        else await route.fulfill({ json: page1 })
        return true
      },
    ])
    await expect(rows(page)).toHaveCount(2)
    fail = true
    await page.getByLabel('Status').selectOption('open')
    await expect(page.getByRole('alert')).toContainText('Could not load orders')
    await expect(page.getByText('No orders match')).toHaveCount(0)
    fail = false
    await page.getByRole('button', { name: 'Retry' }).click()
    await expect(rows(page)).toHaveCount(2)
    expect(listRequests(requests).at(-1)?.query).toEqual({ page: '1', status: 'open', page_size: '20' })
  })
})

test.describe('search and filters', () => {
  test('search sends the trimmed uppercased plate from page 1', async ({ page }) => {
    const requests = await openOrders(page, [ordersApi((q) => (q.page === '2' ? { count: 25, results: [order(3, 'EF789')] } : { count: 25, results: [order(1, 'AB123')] }))])
    await page.getByRole('button', { name: 'Next page' }).click()
    await expect(page.getByText('Page 2 of 2')).toBeVisible()
    const search = page.getByRole('searchbox', { name: 'Search by plate' })
    await search.fill('  ab123 ')
    await search.press('Enter')
    await expect(page.getByText('Page 1 of 2')).toBeVisible()
    expect(listRequests(requests).at(-1)?.query).toEqual({ page: '1', plate: 'AB123', page_size: '20' })
  })

  test('status filter sends the status and All drops it', async ({ page }) => {
    const requests = await openOrders(page)
    await expect(rows(page)).toHaveCount(2)
    await page.getByLabel('Status').selectOption('done')
    await expect.poll(() => listRequests(requests).at(-1)?.query).toEqual({ page: '1', status: 'done', page_size: '20' })
    await page.getByLabel('Status').selectOption('')
    await expect.poll(() => listRequests(requests).length).toBe(3)
    expect(listRequests(requests).at(-1)?.query).toEqual({ page: '1', page_size: '20' })
  })

  test('paging keeps the search and the status', async ({ page }) => {
    const requests = await openOrders(page, [ordersApi((q) => ({ count: 45, results: [order(Number(q.page), `P${q.page}X`)] }))])
    const prev = page.getByRole('button', { name: 'Previous page' })
    await expect(rows(page)).toHaveCount(1)
    await expect(prev).toBeDisabled()
    await page.getByLabel('Status').selectOption('open')
    const search = page.getByRole('searchbox', { name: 'Search by plate' })
    await search.fill('p')
    await search.press('Enter')
    await expect.poll(() => listRequests(requests).length).toBe(3)
    await expect(page.getByText('Page 1 of 3')).toBeVisible()
    const next = page.getByRole('button', { name: 'Next page' })
    await next.click()
    await expect(page.getByText('Page 2 of 3')).toBeVisible()
    expect(listRequests(requests).at(-1)?.query).toEqual({ page: '2', plate: 'P', status: 'open', page_size: '20' })
    await next.click()
    await expect(page.getByText('Page 3 of 3')).toBeVisible()
    await expect(next).toBeDisabled()
    await prev.click()
    await expect(page.getByText('Page 2 of 3')).toBeVisible()
    expect(listRequests(requests).at(-1)?.query).toEqual({ page: '2', plate: 'P', status: 'open', page_size: '20' })
  })
})

test('overdue marks open orders due before today only', async ({ page }) => {
  await page.clock.setFixedTime(new Date('2026-04-10T12:00:00'))
  await openOrders(page, [
    ordersApi(() => ({
      count: 3,
      results: [order(1, 'LATE1', { due_date: '2026-04-09' }), order(2, 'TODAY', { due_date: '2026-04-10' }), order(3, 'DONE1', { due_date: '2026-04-01', status: 'done' })],
    })),
  ])
  await expect(rows(page)).toHaveCount(3)
  await expect(rows(page).filter({ hasText: 'LATE1' })).toContainText('Overdue')
  await expect(rows(page).filter({ hasText: 'TODAY' })).not.toContainText('Overdue')
  await expect(rows(page).filter({ hasText: 'DONE1' })).not.toContainText('Overdue')
})

test('clicking a plate opens the order', async ({ page }) => {
  await openOrders(page, [ordersApi(() => page1), reply('GET', '/orders/2/', order(2, 'CD456'))])
  await page.getByRole('link', { name: 'CD456' }).click()
  await expect(page).toHaveURL('/orders/2')
  await expect(page.getByRole('heading', { name: 'Order CD456' })).toBeVisible()
})

test.describe('roles', () => {
  test('viewers see neither New order nor delete', async ({ page }) => {
    await openOrders(page, undefined, 'viewer')
    await expect(rows(page)).toHaveCount(2)
    await expect(page.getByRole('button', { name: 'New order' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^Delete/ })).toHaveCount(0)
  })

  test('managers see New order and a delete per order', async ({ page }) => {
    await openOrders(page)
    await expect(page.getByRole('button', { name: 'New order' })).toBeVisible()
    await expect(page.getByRole('button', { name: /^Delete/ })).toHaveCount(2)
  })
})

test.describe('delete', () => {
  const deleteApi = (status: number): ApiHandler => async (route, request) => {
    if (request.method !== 'DELETE') return false
    await route.fulfill({ status, body: status === 204 ? '' : '{}' })
    return true
  }

  test('confirming deletes the order and removes its row', async ({ page }) => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    const requests = await openOrders(page, [
      ordersApi(() => page1),
      async (route, request) => {
        if (request.method !== 'DELETE') return false
        await gate
        await route.fulfill({ status: 204, body: '' })
        return true
      },
    ])
    await page.getByRole('button', { name: 'Delete AB123' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Delete order AB123?' })
    await dialog.getByRole('button', { name: 'Delete' }).click()
    await expect(dialog).toBeHidden()
    await expect(rows(page)).toHaveCount(2)
    release()
    await expect(rows(page)).toHaveCount(1)
    await expect(page.getByRole('link', { name: 'AB123' })).toHaveCount(0)
    expect(requests.filter((r) => r.method === 'DELETE').map((r) => r.path)).toEqual(['/orders/1/'])
  })

  test('cancelling sends nothing', async ({ page }) => {
    const requests = await openOrders(page, [ordersApi(() => page1), deleteApi(204)])
    await page.getByRole('button', { name: 'Delete AB123' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Delete order AB123?' })
    await dialog.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).toBeHidden()
    await expect(rows(page)).toHaveCount(2)
    expect(requests.filter((r) => r.method === 'DELETE')).toEqual([])
  })

  test('a failed delete keeps the row and says so', async ({ page }) => {
    await openOrders(page, [ordersApi(() => page1), deleteApi(500)])
    await page.getByRole('button', { name: 'Delete AB123' }).click()
    await page.getByRole('alertdialog').getByRole('button', { name: 'Delete' }).click()
    await expect(page.getByRole('status')).toHaveText('Could not delete order')
    await expect(rows(page)).toHaveCount(2)
  })
})

test.describe('new order', () => {
  const created: ApiHandler = async (route, request) => {
    if (request.method !== 'POST') return false
    await route.fulfill({ status: 201, json: { id: 9 } })
    return true
  }

  const fill = async (page: Page, values: { customer?: string; plate?: string; due?: string }) => {
    await page.getByRole('button', { name: 'New order' }).click()
    const dialog = page.getByRole('dialog', { name: 'New order' })
    if (values.customer !== undefined) await dialog.getByLabel('Customer').fill(values.customer)
    if (values.plate !== undefined) await dialog.getByLabel('Plate').fill(values.plate)
    if (values.due !== undefined) await dialog.getByLabel('Due date').fill(values.due)
    return dialog
  }

  test('creating sends the cleaned order, closes, announces, and reloads', async ({ page }) => {
    let release!: () => void
    const gate = new Promise<void>((r) => (release = r))
    const requests = await openOrders(page, [
      ordersApi(() => page1),
      async (route, request) => {
        if (request.method !== 'POST') return false
        await gate
        await route.fulfill({ status: 201, json: { id: 9 } })
        return true
      },
    ])
    await expect(rows(page)).toHaveCount(2)
    const dialog = await fill(page, { customer: '  Jan Kowalski ', plate: ' xy99 ', due: '2026-12-01' })
    await dialog.getByRole('button', { name: 'Create' }).click()
    await expect(dialog.getByRole('button', { name: 'Create' })).toBeDisabled()
    release()
    await expect(dialog).toBeHidden()
    await expect(page.getByRole('status')).toHaveText('Order created')
    await expect.poll(() => listRequests(requests).length).toBe(2)
    expect(requests.filter((r) => r.method === 'POST')).toEqual([
      { method: 'POST', path: '/orders/', query: {}, body: { customer: 'Jan Kowalski', plate: 'XY99', due_date: '2026-12-01' } },
    ])
  })

  for (const [name, values, field, error] of [
    ['customer is required', { plate: 'XY99', due: '2026-12-01' }, 'customer', 'Enter the customer'],
    ['plate format is checked', { customer: 'Jan', plate: 'X', due: '2026-12-01' }, 'plate', 'Use 2–8 letters or digits'],
    ['due date is required', { customer: 'Jan', plate: 'XY99' }, 'due', 'Pick the due date'],
  ] as const) {
    test(`${name}, and nothing is sent`, async ({ page }) => {
      const requests = await openOrders(page, [ordersApi(() => page1), created])
      const dialog = await fill(page, values)
      await dialog.getByRole('button', { name: 'Create' }).click()
      await expect(dialog.getByText(error)).toBeVisible()
      expect(requests.filter((r) => r.method === 'POST')).toEqual([])
      expect(field).toBeTruthy()
    })
  }

  test('server field errors show and the dialog stays open', async ({ page }) => {
    await openOrders(page, [ordersApi(() => page1), reply('POST', '/orders/', { plate: ['Plate already has an open order'] }, 400)])
    const dialog = await fill(page, { customer: 'Jan', plate: 'AB123', due: '2026-12-01' })
    await dialog.getByRole('button', { name: 'Create' }).click()
    await expect(dialog.getByText('Plate already has an open order')).toBeVisible()
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('button', { name: 'Create' })).toBeEnabled()
  })
})
