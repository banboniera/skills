import { expect, test } from '@playwright/test'

import { openPage, reply, users } from './helpers'

const orders = { count: 0, results: [] }

test('signing in stores the session and opens the page the user asked for', async ({ page }) => {
  const requests = await openPage(page, '/login?next=/orders', {
    role: null,
    api: [reply('POST', '/auth/login/', { token: 't1', user: users.viewer }), reply('GET', '/orders/', orders)],
  })

  await page.getByLabel('Email').fill(' victor@example.com ')
  await page.getByLabel('Password').fill('secret')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('heading', { name: 'Orders' })).toBeVisible()
  await expect(page).toHaveURL('/orders')
  expect(requests.filter((r) => r.method === 'POST')).toEqual([
    { method: 'POST', path: '/auth/login/', query: {}, body: { email: 'victor@example.com', password: 'secret' } },
  ])
})

test('a rejected password keeps the user on the login page', async ({ page }) => {
  await openPage(page, '/login', {
    role: null,
    api: [reply('POST', '/auth/login/', { non_field_errors: ['Invalid credentials'] }, 400)],
  })

  await page.getByLabel('Email').fill('victor@example.com')
  await page.getByLabel('Password').fill('wrong')
  await page.getByRole('button', { name: 'Sign in' }).click()

  await expect(page.getByRole('alert')).toHaveText('Wrong email or password')
  await expect(page).toHaveURL('/login')
})

test('a signed-out visitor is sent to the login page', async ({ page }) => {
  await openPage(page, '/orders', { role: null })

  await expect(page.getByRole('heading', { name: 'Sign in' })).toBeVisible()
  await expect(page).toHaveURL('/login?next=%2Forders')
})
