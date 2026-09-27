/**
 * Billing API (RTK Query), served under /api.
 *
 * - listInvoices({ page, status, search }): GET /api/invoices/?page=<n>&page_size=25, plus `status` unless it is "all",
 *   plus `search` (trimmed) unless it is blank. Answers { count, results: Invoice[] }. Tagged as the invoice list.
 * - getInvoice(id): GET /api/invoices/<id>/.
 * - updateInvoice({ id, ...changes }): PATCH /api/invoices/<id>/ with only the changed fields as the JSON body.
 *   Refreshes that invoice and the lists.
 * - markPaid({ id, paidOn }): POST /api/invoices/<id>/pay/ with { paid_on: "YYYY-MM-DD" }. Refreshes that invoice and the lists.
 */
import { createApi, fetchBaseQuery } from '@reduxjs/toolkit/query/react'

export type InvoiceStatus = 'draft' | 'sent' | 'paid'

export interface Invoice {
  id: number
  number: string
  customer: string
  amount_cents: number
  status: InvoiceStatus
  due_date: string
  notes?: string
}

export interface InvoiceList {
  count: number
  results: Invoice[]
}

export interface ListArgs {
  page: number
  status: InvoiceStatus | 'all'
  search?: string
}

export const PAGE_SIZE = 25

export const api = createApi({
  reducerPath: 'api',
  baseQuery: fetchBaseQuery({ baseUrl: '/api' }),
  tagTypes: ['Invoice'],
  endpoints: (build) => ({
    listInvoices: build.query<InvoiceList, ListArgs>({
      query: ({ page, status, search }) => {
        const params: Record<string, string | number> = { page, page_size: PAGE_SIZE, status }
        const text = search?.trim()
        if (text) params.search = text
        return { url: '/invoices/', params }
      },
      providesTags: [{ type: 'Invoice', id: 'LIST' }],
    }),
    getInvoice: build.query<Invoice, number>({
      query: (id) => `/invoices/${id}/`,
      providesTags: (_result, _error, id) => [{ type: 'Invoice', id }],
    }),
    updateInvoice: build.mutation<Invoice, Partial<Invoice> & { id: number }>({
      query: ({ id, ...changes }) => ({ url: `/invoices/${id}/`, method: 'PATCH', body: changes }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'Invoice', id }, { type: 'Invoice', id: 'LIST' }],
    }),
    markPaid: build.mutation<Invoice, { id: number; paidOn: string }>({
      query: ({ id, paidOn }) => ({ url: `/invoices/${id}/pay/`, method: 'POST', body: { paid_on: paidOn } }),
      invalidatesTags: (_result, _error, { id }) => [{ type: 'Invoice', id }, { type: 'Invoice', id: 'LIST' }],
    }),
  }),
})

export const { useListInvoicesQuery, useGetInvoiceQuery, useUpdateInvoiceMutation, useMarkPaidMutation } = api
