import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { InvoiceForm } from './InvoiceForm'

const fillValid = (container: HTMLElement) => {
  fireEvent.change(screen.getByLabelText('Customer'), { target: { value: 'Acme' } })
  fireEvent.change(screen.getByLabelText('Amount'), { target: { value: '12.50' } })
  fireEvent.change(container.querySelector('input[type=date]') as Element, { target: { value: '2026-05-01' } })
}

describe('InvoiceForm', () => {
  it('renders', () => {
    render(<InvoiceForm onSubmit={vi.fn()} onDone={vi.fn()} />)
    expect(screen.getByText('New invoice')).toBeTruthy()
  })

  it('submits', async () => {
    const onSubmit = vi.fn(() => Promise.resolve())
    const { container } = render(<InvoiceForm onSubmit={onSubmit} onDone={vi.fn()} />)
    fillValid(container)
    fireEvent.click(screen.getByText('Save'))
    expect(onSubmit).toHaveBeenCalled()
  })

  it('validates the customer', () => {
    render(<InvoiceForm onSubmit={vi.fn()} onDone={vi.fn()} />)
    fireEvent.click(screen.getByText('Save'))
    expect(screen.getByText('Enter the customer')).toBeInTheDocument()
  })

  it('keeps the form locked after server field errors', async () => {
    const onSubmit = vi.fn(() => Promise.reject({ fieldErrors: { customer: ['Unknown customer'] } }))
    const { container } = render(<InvoiceForm onSubmit={onSubmit} onDone={vi.fn()} />)
    fillValid(container)
    fireEvent.click(screen.getByText('Save'))
    expect(await screen.findByText('Unknown customer')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Saving…' })).toBeDisabled()
  })
})
