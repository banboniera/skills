import { expect, test, type Page } from '@playwright/test'

import { openPage, reply, users, type ApiHandler, type RecordedRequest, type Role } from './helpers'

test.use({ timezoneId: 'Europe/Warsaw' })

// 2026-04-10 01:30 in Warsaw is still 2026-04-09 in UTC.
const NOW = new Date('2026-04-10T01:30:00+02:00')

type Booking = { id: number; room: { id: number; name: string }; title: string; owner: { id: number; name: string }; starts_at: string; ends_at: string; status: string }
const booking = (id: number, title: string, owner: { id: number; name: string }, starts: string, ends: string, status = 'booked'): Booking => ({
  id, room: { id: 3, name: 'Blue room' }, title, owner: { id: owner.id, name: owner.name }, starts_at: starts, ends_at: ends, status,
})
const other = { id: 42, name: 'Olga Other' }
// Local 14:00–15:00 and 09:30–10:00 in Warsaw (UTC+2).
const day = [booking(1, 'Retro', users.member, '2026-04-10T12:00:00Z', '2026-04-10T13:00:00Z'), booking(2, 'Standup', other, '2026-04-10T07:30:00Z', '2026-04-10T08:00:00Z')]

const bookingsApi = (pick: (q: Record<string, string>) => Booking[] = () => day): ApiHandler => async (route, request) => {
  if (request.method !== 'GET' || request.path !== '/bookings/') return false
  await route.fulfill({ json: pick(request.query) })
  return true
}
const roomsApi = reply('GET', '/rooms/', [{ id: 3, name: 'Blue room' }, { id: 4, name: 'Red room' }])
const gets = (requests: RecordedRequest[]) => requests.filter((r) => r.method === 'GET' && r.path === '/bookings/')
const items = (page: Page) => page.getByRole('list', { name: 'Bookings' }).getByRole('listitem')

const open = async (page: Page, api: ApiHandler[] = [bookingsApi(), roomsApi], role: Role = 'member') => {
  await page.clock.setFixedTime(NOW)
  return openPage(page, '/bookings', { role, api })
}

test('opens on the local day, sorted, with local times', async ({ page }) => {
  const requests = await open(page)
  await expect(page.getByRole('heading', { name: 'Bookings for 2026-04-10' })).toBeVisible()
  await expect(items(page)).toHaveCount(2)
  await expect(items(page).nth(0)).toContainText('Standup')
  await expect(items(page).nth(0)).toContainText('09:30–10:00')
  await expect(items(page).nth(1)).toContainText('14:00–15:00')
  expect(gets(requests)[0].query).toEqual({ date: '2026-04-10' })
})

test('day navigation moves one day and keeps only mine', async ({ page }) => {
  const requests = await open(page)
  await expect(items(page)).toHaveCount(2)
  await page.getByLabel('Only mine').check()
  await expect.poll(() => gets(requests).at(-1)?.query).toEqual({ date: '2026-04-10', owner: 'me' })
  await page.getByRole('button', { name: 'Next day' }).click()
  await expect(page.getByRole('heading', { name: 'Bookings for 2026-04-11' })).toBeVisible()
  await expect.poll(() => gets(requests).at(-1)?.query).toEqual({ date: '2026-04-11', owner: 'me' })
  await page.getByRole('button', { name: 'Previous day' }).click()
  await page.getByRole('button', { name: 'Previous day' }).click()
  await expect(page.getByRole('heading', { name: 'Bookings for 2026-04-09' })).toBeVisible()
  await expect.poll(() => gets(requests).at(-1)?.query).toEqual({ date: '2026-04-09', owner: 'me' })
})

test('empty day and failed load', async ({ page }) => {
  let fail = false
  await open(page, [bookingsApi(() => []), async (route, request) => {
    if (!fail || request.path !== '/bookings/') return false
    await route.fulfill({ status: 500, json: {} })
    return true
  }].reverse())
  await expect(page.getByText('No bookings on this day')).toBeVisible()
  fail = true
  await page.getByRole('button', { name: 'Next day' }).click()
  await expect(page.getByRole('alert')).toHaveText('Could not load bookings')
  await expect(page.getByText('No bookings on this day')).toHaveCount(0)
})

test.describe('who can book and cancel', () => {
  test('guests can neither book nor cancel', async ({ page }) => {
    await open(page, undefined, 'guest')
    await expect(items(page)).toHaveCount(2)
    await expect(page.getByRole('button', { name: 'Book a room' })).toHaveCount(0)
    await expect(page.getByRole('button', { name: /^Cancel/ })).toHaveCount(0)
  })

  test('members cancel only their own bookings', async ({ page }) => {
    await open(page)
    await expect(items(page)).toHaveCount(2)
    await expect(page.getByRole('button', { name: 'Book a room' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cancel Retro' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cancel Standup' })).toHaveCount(0)
  })

  test('admins cancel anyone’s booking, but not cancelled ones', async ({ page }) => {
    await open(page, [bookingsApi(() => [...day, booking(3, 'Old', other, '2026-04-10T15:00:00Z', '2026-04-10T16:00:00Z', 'cancelled')]), roomsApi], 'admin')
    await expect(items(page)).toHaveCount(3)
    await expect(page.getByRole('button', { name: 'Cancel Retro' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cancel Standup' })).toBeVisible()
    await expect(page.getByRole('button', { name: 'Cancel Old' })).toHaveCount(0)
  })
})

test.describe('cancel', () => {
  const cancelApi: ApiHandler = async (route, request) => {
    if (request.method !== 'POST') return false
    await route.fulfill({ json: {} })
    return true
  }

  test('confirming cancels and marks the booking', async ({ page }) => {
    const requests = await open(page, [bookingsApi(), cancelApi])
    await page.getByRole('button', { name: 'Cancel Retro' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Cancel Retro?' })
    await dialog.getByRole('button', { name: 'Cancel booking' }).click()
    const retro = items(page).filter({ hasText: 'Retro' })
    await expect(retro).toContainText('Cancelled')
    await expect(page.getByRole('button', { name: 'Cancel Retro' })).toHaveCount(0)
    expect(requests.filter((r) => r.method !== 'GET').map((r) => `${r.method} ${r.path}`)).toEqual(['POST /bookings/1/cancel/'])
  })

  test('keep sends nothing', async ({ page }) => {
    const requests = await open(page, [bookingsApi(), cancelApi])
    await page.getByRole('button', { name: 'Cancel Retro' }).click()
    const dialog = page.getByRole('alertdialog', { name: 'Cancel Retro?' })
    await dialog.getByRole('button', { name: 'Keep' }).click()
    await expect(dialog).toBeHidden()
    await expect(items(page).filter({ hasText: 'Retro' })).not.toContainText('Cancelled')
    expect(requests.filter((r) => r.method !== 'GET')).toEqual([])
  })
})

test.describe('book a room', () => {
  const fill = async (page: Page, title: string, start: string, end: string) => {
    await page.getByRole('button', { name: 'Book a room' }).click()
    const dialog = page.getByRole('dialog', { name: 'Book a room' })
    await dialog.getByLabel('Room').selectOption('Red room')
    await dialog.getByLabel('Title').fill(title)
    await dialog.getByLabel('Start').fill(start)
    await dialog.getByLabel('End').fill(end)
    await dialog.getByRole('button', { name: 'Book' }).click()
    return dialog
  }

  test('booking sends UTC instants, closes, announces, reloads', async ({ page }) => {
    const requests = await open(page, [bookingsApi(), roomsApi, reply('POST', '/bookings/', { id: 9 }, 201)])
    await expect(items(page)).toHaveCount(2)
    const dialog = await fill(page, '  Planning ', '11:00', '12:30')
    await expect(dialog).toBeHidden()
    await expect(page.getByRole('status')).toHaveText('Room booked')
    await expect.poll(() => gets(requests).length).toBe(2)
    expect(requests.filter((r) => r.method === 'POST').map((r) => r.body)).toEqual([
      { room: 4, title: 'Planning', starts_at: '2026-04-10T09:00:00.000Z', ends_at: '2026-04-10T10:30:00.000Z' },
    ])
  })

  for (const [name, title, start, end, message] of [
    ['a title is required', ' ', '11:00', '12:00', 'Enter a title'],
    ['the end must be after the start', 'Planning', '11:00', '11:00', 'End after the start'],
    ['the end cannot be before the start', 'Planning', '11:00', '10:00', 'End after the start'],
  ] as const) {
    test(`${name}, and nothing is sent`, async ({ page }) => {
      const requests = await open(page, [bookingsApi(), roomsApi, reply('POST', '/bookings/', { id: 9 }, 201)])
      const dialog = await fill(page, title, start, end)
      await expect(dialog.getByText(message)).toBeVisible()
      expect(requests.filter((r) => r.method === 'POST')).toEqual([])
    })
  }

  test('a conflict keeps the dialog open with the reason', async ({ page }) => {
    await open(page, [bookingsApi(), roomsApi, reply('POST', '/bookings/', { detail: 'conflict' }, 409)])
    const dialog = await fill(page, 'Planning', '11:00', '12:00')
    await expect(dialog.getByText('That room is already booked then')).toBeVisible()
    await expect(dialog).toBeVisible()
  })
})
