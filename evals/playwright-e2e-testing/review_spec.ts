import { expect, test } from '@playwright/test'

import { openPage, reply } from './helpers'

const orders = {
  count: 2,
  results: [
    { id: 1, customer: 'Jan Kowalski', plate: 'AB123', status: 'open', due_date: '2026-05-01' },
    { id: 2, customer: 'Anna Nowak', plate: 'CD456', status: 'done', due_date: '2026-05-02' },
  ],
}

test('lists orders', async ({ page }) => {
  await openPage(page, '/orders', { api: [reply('GET', '/orders/', orders)] })
  await expect(page.locator('table tbody tr')).toHaveCount(2)
})

test('search by plate', async ({ page }) => {
  await openPage(page, '/orders', { api: [reply('GET', '/orders/', orders)] })
  await page.getByPlaceholder('Search by plate').fill('ab123')
  await page.getByPlaceholder('Search by plate').press('Enter')
  await expect(page.getByRole('cell', { name: 'Jan Kowalski' })).toBeVisible()
})

test('status filter reloads the list', async ({ page }) => {
  const requests = await openPage(page, '/orders', { api: [reply('GET', '/orders/', orders)] })
  await page.getByLabel('Status').selectOption('done')
  await expect.poll(() => requests.length).toBeGreaterThan(1)
})

test('next page', async ({ page }) => {
  const requests = await openPage(page, '/orders', { api: [reply('GET', '/orders/', { ...orders, count: 30 })] })
  await page.getByRole('button', { name: 'Next page' }).click()
  await expect.poll(() => requests.at(-1)?.query.page).toBe('2')
})

test('shows empty state', async ({ page }) => {
  await openPage(page, '/orders', { api: [reply('GET', '/orders/', { count: 0, results: [] })] })
  expect(await page.getByText('No orders match').isVisible()).toBe(true)
})

test('shows loading state', async ({ page }) => {
  await openPage(page, '/orders', { api: [reply('GET', '/orders/', orders)] })
  await expect(page.getByText('Loading orders…')).toBeHidden()
})

test('marks overdue orders', async ({ page }) => {
  const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString().slice(0, 10)
  const late = { count: 1, results: [{ ...orders.results[0], due_date: yesterday }] }
  await openPage(page, '/orders', { api: [reply('GET', '/orders/', late)] })
  await expect(page.locator('.badge')).toHaveText('Overdue')
})

test('viewers do not see New order', async ({ page }) => {
  await openPage(page, '/orders', { role: 'viewer', api: [reply('GET', '/orders/', orders)] })
  await expect(page.getByRole('button', { name: 'New order' })).toBeHidden()
})

test('each order has a delete button', async ({ page }) => {
  await openPage(page, '/orders', { role: 'viewer', api: [reply('GET', '/orders/', orders)] })
  await expect(page.getByRole('button', { name: 'Delete AB123' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'Delete CD456' })).toBeVisible()
})

test('delete an order', async ({ page }) => {
  await openPage(page, '/orders', { api: [reply('GET', '/orders/', orders), reply('DELETE', '/orders/1/', null, 204)] })
  await page.getByRole('button', { name: /Delete/ }).nth(0).click()
  await page.getByRole('button', { name: 'Delete', exact: true }).click()
  await expect(page.getByRole('alertdialog')).toBeHidden()
})

test('create an order', async ({ page }) => {
  const requests = await openPage(page, '/orders', { api: [reply('GET', '/orders/', orders), reply('POST', '/orders/', { id: 3 }, 201)] })
  await page.getByRole('button', { name: 'New order' }).click()
  await page.getByLabel('Customer').fill('Piotr Zieliński')
  await page.getByLabel('Plate', { exact: true }).fill('ef789')
  await page.getByLabel('Due date').fill('2026-06-01')
  await page.getByRole('button', { name: 'Create' }).click()
  await page.waitForTimeout(500)
  expect(requests.find((r) => r.method === 'POST')?.body).toEqual(expect.objectContaining({ customer: 'Piotr Zieliński' }))
})

test('customer is required', async ({ page }) => {
  await openPage(page, '/orders', { api: [reply('GET', '/orders/', orders)] })
  await page.getByRole('button', { name: 'New order' }).click()
  await page.getByLabel('Plate', { exact: true }).fill('EF789')
  await page.getByLabel('Due date').fill('2026-06-01')
  await page.getByRole('button', { name: 'Create' }).click()
  await expect(page.getByText('Enter the customer')).toBeVisible()
})
