import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { InvoiceForm, type InvoiceInput } from './InvoiceForm'

const setup = (props: Partial<Parameters<typeof InvoiceForm>[0]> = {}) => {
  const onSubmit = vi.fn<(input: InvoiceInput) => Promise<unknown>>(() => Promise.resolve())
  const onDone = vi.fn()
  const user = userEvent.setup()
  render(<InvoiceForm onSubmit={onSubmit} onDone={onDone} {...props} />)
  return { user, onSubmit: props.onSubmit ?? onSubmit, onDone }
}

const fill = async (user: ReturnType<typeof userEvent.setup>, values: { customer?: string; amount?: string; due?: string; notes?: string }) => {
  if (values.customer !== undefined) await user.type(screen.getByLabelText('Customer'), values.customer)
  if (values.amount !== undefined) await user.type(screen.getByLabelText('Amount'), values.amount)
  if (values.due !== undefined) await user.type(screen.getByLabelText('Due date'), values.due)
  if (values.notes !== undefined) await user.type(screen.getByLabelText('Notes'), values.notes)
}

const deferred = () => {
  let resolve!: (value?: unknown) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

describe('InvoiceForm', () => {
  it('starts empty for a new invoice', () => {
    setup()
    expect(screen.getByRole('heading', { name: 'New invoice' })).toBeInTheDocument()
    expect(screen.getByLabelText('Customer')).toHaveValue('')
    expect(screen.getByLabelText('Amount')).toHaveValue('')
  })

  it('starts from the invoice being edited', () => {
    setup({ invoice: { number: 'A-7', customer: 'Acme', amount_cents: 1205, due_date: '2026-05-01', notes: 'Net 30' } })
    expect(screen.getByRole('heading', { name: 'Edit invoice A-7' })).toBeInTheDocument()
    expect(screen.getByLabelText('Customer')).toHaveValue('Acme')
    expect(screen.getByLabelText('Amount')).toHaveValue('12.05')
    expect(screen.getByLabelText('Due date')).toHaveValue('2026-05-01')
    expect(screen.getByLabelText('Notes')).toHaveValue('Net 30')
  })

  it('submits the cleaned values and then finishes', async () => {
    const { user, onSubmit, onDone } = setup()
    await fill(user, { customer: '  Acme ', amount: '12,5', due: '2026-05-01', notes: '  Net 30 ' })
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ customer: 'Acme', amount_cents: 1250, due_date: '2026-05-01', notes: 'Net 30' })
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledOnce())
  })

  it('leaves out blank notes', async () => {
    const { user, onSubmit } = setup()
    await fill(user, { customer: 'Acme', amount: '1', due: '2026-05-01', notes: '   ' })
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith({ customer: 'Acme', amount_cents: 100, due_date: '2026-05-01' })
  })

  it.each([
    ['a missing customer', { amount: '1', due: '2026-05-01' }, 'Enter the customer'],
    ['a blank customer', { customer: '   ', amount: '1', due: '2026-05-01' }, 'Enter the customer'],
    ['a missing amount', { customer: 'Acme', due: '2026-05-01' }, 'Enter an amount above zero'],
    ['a zero amount', { customer: 'Acme', amount: '0', due: '2026-05-01' }, 'Enter an amount above zero'],
    ['an unreadable amount', { customer: 'Acme', amount: '12.345', due: '2026-05-01' }, 'Enter an amount above zero'],
    ['a missing due date', { customer: 'Acme', amount: '1' }, 'Pick the due date'],
  ])('refuses %s and submits nothing', async (_name, values, message) => {
    const { user, onSubmit, onDone } = setup()
    await fill(user, values)
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByText(message)).toBeInTheDocument()
    expect(onSubmit).not.toHaveBeenCalled()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('accepts the smallest amount above zero', async () => {
    const { user, onSubmit } = setup()
    await fill(user, { customer: 'Acme', amount: '0.01', due: '2026-05-01' })
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({ amount_cents: 1 }))
  })

  it('disables Save while saving', async () => {
    const save = deferred()
    const { user, onDone } = setup({ onSubmit: vi.fn(() => save.promise) })
    await fill(user, { customer: 'Acme', amount: '1', due: '2026-05-01' })
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
    expect(onDone).not.toHaveBeenCalled()
    save.resolve()
    await vi.waitFor(() => expect(onDone).toHaveBeenCalledOnce())
  })

  it('shows server field errors, keeps the values, and lets the user save again', async () => {
    const onSubmit = vi.fn(() => Promise.reject({ fieldErrors: { customer: ['Unknown customer'] } }))
    const { user, onDone } = setup({ onSubmit })
    await fill(user, { customer: 'Acme', amount: '1', due: '2026-05-01' })
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByText('Unknown customer')).toBeInTheDocument()
    expect(screen.getByLabelText('Customer')).toHaveValue('Acme')
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('shows a general error for any other failure', async () => {
    const { user, onDone } = setup({ onSubmit: vi.fn(() => Promise.reject(new Error('offline'))) })
    await fill(user, { customer: 'Acme', amount: '1', due: '2026-05-01' })
    await user.click(screen.getByRole('button', { name: 'Save' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not save the invoice')
    expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled()
    expect(onDone).not.toHaveBeenCalled()
  })

  it('cancels without submitting', async () => {
    const { user, onSubmit, onDone } = setup()
    await fill(user, { customer: 'Acme' })
    await user.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onDone).toHaveBeenCalledOnce()
    expect(onSubmit).not.toHaveBeenCalled()
  })
})
