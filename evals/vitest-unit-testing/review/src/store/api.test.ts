import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from './api'
import { makeStore } from './index'

const fetchMock = vi.fn(async () => Response.json({ count: 0, results: [] }))

beforeEach(() => vi.stubGlobal('fetch', fetchMock))
afterEach(() => vi.unstubAllGlobals())

describe('api', () => {
  it('lists invoices', async () => {
    const store = makeStore()
    await store.dispatch(api.endpoints.listInvoices.initiate({ page: 1, status: 'sent' }))
    expect(fetchMock).toHaveBeenCalled()
  })

  it('rejects paying an invoice twice', async () => {
    const store = makeStore()
    await store
      .dispatch(api.endpoints.markPaid.initiate({ id: 7, paidOn: '2026-04-10' }))
      .unwrap()
      .catch((error) => {
        expect(error.status).toBe(409)
      })
  })
})
