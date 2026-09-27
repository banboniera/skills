import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { makeStore } from './index'
import { api } from './api'

interface Sent {
  method: string
  path: string
  query: Record<string, string>
  body: unknown
}

let sent: Sent[]
let respond: (request: Request) => Response

beforeEach(() => {
  sent = []
  respond = () => Response.json({})
  vi.stubGlobal('fetch', async (input: RequestInfo, init?: RequestInit) => {
    const request = new Request(input, init)
    const url = new URL(request.url)
    const text = await request.clone().text()
    sent.push({ method: request.method, path: url.pathname, query: Object.fromEntries(url.searchParams), body: text ? JSON.parse(text) : undefined })
    return respond(request)
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('listInvoices', () => {
  it.each([
    [{ page: 1, status: 'all' as const }, { page: '1', page_size: '25' }],
    [{ page: 2, status: 'sent' as const }, { page: '2', page_size: '25', status: 'sent' }],
    [{ page: 1, status: 'all' as const, search: '  acme ' }, { page: '1', page_size: '25', search: 'acme' }],
    [{ page: 1, status: 'paid' as const, search: '   ' }, { page: '1', page_size: '25', status: 'paid' }],
  ])('sends %j as %j', async (args, query) => {
    respond = () => Response.json({ count: 0, results: [] })
    const store = makeStore()
    const result = await store.dispatch(api.endpoints.listInvoices.initiate(args)).unwrap()
    expect(result).toEqual({ count: 0, results: [] })
    expect(sent).toEqual([{ method: 'GET', path: '/api/invoices/', query, body: undefined }])
  })
})

describe('updateInvoice', () => {
  it('patches only the changed fields and refetches the list', async () => {
    const store = makeStore()
    respond = () => Response.json({ count: 0, results: [] })
    const list = store.dispatch(api.endpoints.listInvoices.initiate({ page: 1, status: 'all' }))
    await list
    respond = () => Response.json({ id: 7 })
    await store.dispatch(api.endpoints.updateInvoice.initiate({ id: 7, notes: 'Paid by card' })).unwrap()
    await vi.waitFor(() => expect(sent).toHaveLength(3))
    expect(sent[1]).toEqual({ method: 'PATCH', path: '/api/invoices/7/', query: {}, body: { notes: 'Paid by card' } })
    expect(sent[2]).toMatchObject({ method: 'GET', path: '/api/invoices/' })
    list.unsubscribe()
  })
})

describe('markPaid', () => {
  it('posts the payment date and refetches the invoice', async () => {
    const store = makeStore()
    respond = () => Response.json({ id: 7 })
    const detail = store.dispatch(api.endpoints.getInvoice.initiate(7))
    await detail
    await store.dispatch(api.endpoints.markPaid.initiate({ id: 7, paidOn: '2026-04-10' })).unwrap()
    await vi.waitFor(() => expect(sent).toHaveLength(3))
    expect(sent[1]).toEqual({ method: 'POST', path: '/api/invoices/7/pay/', query: {}, body: { paid_on: '2026-04-10' } })
    expect(sent[2]).toMatchObject({ method: 'GET', path: '/api/invoices/7/' })
    detail.unsubscribe()
  })

  it('rejects when the API refuses', async () => {
    respond = () => Response.json({ detail: 'Already paid' }, { status: 409 })
    const store = makeStore()
    await expect(store.dispatch(api.endpoints.markPaid.initiate({ id: 7, paidOn: '2026-04-10' })).unwrap()).rejects.toMatchObject({
      status: 409,
      data: { detail: 'Already paid' },
    })
  })
})

describe('getInvoice', () => {
  it('gets one invoice by id', async () => {
    respond = () => Response.json({ id: 3, number: 'A-3' })
    const store = makeStore()
    const result = await store.dispatch(api.endpoints.getInvoice.initiate(3)).unwrap()
    expect(result).toEqual({ id: 3, number: 'A-3' })
    expect(sent).toEqual([{ method: 'GET', path: '/api/invoices/3/', query: {}, body: undefined }])
  })
})
