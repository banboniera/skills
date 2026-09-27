/**
 * Form for creating or editing an invoice.
 *
 * - Fields: Customer (required), Amount (required, parsed with parseAmount, must be above zero), Due date (required),
 *   and Notes (optional). With `invoice`, the fields start from it (the amount shown as "12.50") and the title reads
 *   "Edit invoice <number>"; without it they start empty and the title reads "New invoice".
 * - "Save" checks the fields first. Each invalid field shows its error under it ("Enter the customer",
 *   "Enter an amount above zero", "Pick the due date") and nothing is submitted.
 * - A valid form calls `onSubmit` with { customer (trimmed), amount_cents, due_date, notes (trimmed) }, leaving out
 *   notes when blank. While `onSubmit` is pending, "Save" is disabled and reads "Saving…".
 * - When `onSubmit` rejects with { fieldErrors: { field: [messages] } }, the messages show under their fields,
 *   "Save" is enabled again, and the typed values stay. Any other rejection shows "Could not save the invoice".
 * - When `onSubmit` resolves, `onDone` is called.
 * - "Cancel" calls `onDone` without submitting.
 */
import { type FormEvent, useId, useState } from 'react'

import { parseAmount } from '../utils/money'

export interface InvoiceInput {
  customer: string
  amount_cents: number
  due_date: string
  notes?: string
}

type Field = 'customer' | 'amount_cents' | 'due_date' | 'notes'
type Errors = Partial<Record<Field | 'form', string>>

interface Props {
  invoice?: { number: string } & InvoiceInput
  onSubmit: (input: InvoiceInput) => Promise<unknown>
  onDone: () => void
}

const centsToText = (cents: number) => `${Math.floor(cents / 100)}.${String(cents % 100).padStart(2, '0')}`

export function InvoiceForm({ invoice, onSubmit, onDone }: Props) {
  const id = useId()
  const [customer, setCustomer] = useState(invoice?.customer ?? '')
  const [amount, setAmount] = useState(invoice ? centsToText(invoice.amount_cents) : '')
  const [dueDate, setDueDate] = useState(invoice?.due_date ?? '')
  const [notes, setNotes] = useState(invoice?.notes ?? '')
  const [errors, setErrors] = useState<Errors>({})
  const [saving, setSaving] = useState(false)

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    const cents = parseAmount(amount)
    const found: Errors = {}
    if (!customer.trim()) found.customer = 'Enter the customer'
    if (cents === null || cents <= 0) found.amount_cents = 'Enter an amount above zero'
    if (!dueDate) found.due_date = 'Pick the due date'
    setErrors(found)
    if (Object.keys(found).length > 0 || cents === null) return

    const input: InvoiceInput = { customer: customer.trim(), amount_cents: cents, due_date: dueDate }
    if (notes.trim()) input.notes = notes.trim()
    setSaving(true)
    try {
      await onSubmit(input)
      setSaving(false)
      onDone()
    } catch (failure) {
      const fieldErrors = (failure as { fieldErrors?: Record<string, string[]> })?.fieldErrors
      if (fieldErrors) {
        setErrors(Object.fromEntries(Object.entries(fieldErrors).map(([field, messages]) => [field, messages.join(' ')])))
      } else {
        setErrors({ form: 'Could not save the invoice' })
      }
      setSaving(false)
    }
  }

  const field = (name: Field, label: string, input: React.ReactNode) => (
    <p>
      <label htmlFor={`${id}-${name}`}>{label}</label>
      {input}
      {errors[name] && (
        <span id={`${id}-${name}-error`} className="error">
          {errors[name]}
        </span>
      )}
    </p>
  )

  const described = (name: Field) =>
    errors[name] ? { 'aria-invalid': true, 'aria-describedby': `${id}-${name}-error` } : {}

  return (
    <form onSubmit={submit} aria-labelledby={`${id}-title`} noValidate>
      <h2 id={`${id}-title`}>{invoice ? `Edit invoice ${invoice.number}` : 'New invoice'}</h2>
      {field('customer', 'Customer', <input id={`${id}-customer`} value={customer} onChange={(e) => setCustomer(e.target.value)} {...described('customer')} />)}
      {field('amount_cents', 'Amount', <input id={`${id}-amount_cents`} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} {...described('amount_cents')} />)}
      {field('due_date', 'Due date', <input id={`${id}-due_date`} type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} {...described('due_date')} />)}
      {field('notes', 'Notes', <textarea id={`${id}-notes`} value={notes} onChange={(e) => setNotes(e.target.value)} {...described('notes')} />)}
      {errors.form && <p role="alert">{errors.form}</p>}
      <button type="button" onClick={onDone}>
        Cancel
      </button>
      <button type="submit" disabled={saving}>
        {saving ? 'Saving…' : 'Save'}
      </button>
    </form>
  )
}
