"""Planted bugs and mutants for each eval fixture. Fixes turn the shipped (buggy) sources into correct code.
Fixes and mutants are (file, find, replace); each find must occur exactly once in its file.
"""

MONEY = "src/utils/money.ts"
HOOK = "src/hooks/useDebouncedValue.ts"
API = "src/store/api.ts"
FORM = "src/components/InvoiceForm.tsx"

# Bug 1: a one-digit fraction is read as cents, so "12.5" becomes 1205 instead of 1250.
BUGGY_FRACTION = "Number(fraction || '0')"
FIXED_FRACTION = "Number(fraction.padEnd(2, '0'))"
# Bug 2: after the server rejects with field errors, Save stays disabled.
BUGGY_SAVING = """        setErrors(Object.fromEntries(Object.entries(fieldErrors).map(([field, messages]) => [field, messages.join(' ')])))
      } else {
        setErrors({ form: 'Could not save the invoice' })
        setSaving(false)
      }"""
FIXED_SAVING = """        setErrors(Object.fromEntries(Object.entries(fieldErrors).map(([field, messages]) => [field, messages.join(' ')])))
      } else {
        setErrors({ form: 'Could not save the invoice' })
      }
      setSaving(false)"""
# Bug 3: the list sends status=all instead of leaving the status out.
BUGGY_STATUS = "const params: Record<string, string | number> = { page, page_size: PAGE_SIZE, status }"
FIXED_STATUS = "const params: Record<string, string | number> = { page, page_size: PAGE_SIZE }\n        if (status !== 'all') params.status = status"
BILLING_FIXES = [(MONEY, BUGGY_FRACTION, FIXED_FRACTION), (FORM, BUGGY_SAVING, FIXED_SAVING), (API, BUGGY_STATUS, FIXED_STATUS)]

BILLING_MUTANTS = [
    ("thousands separator missing", MONEY, ".replace(/\\B(?=(\\d{3})+(?!\\d))/g, ',')", ""),
    ("cents not padded", MONEY, "String(abs % 100).padStart(2, '0')", "String(abs % 100)"),
    ("negative sign dropped", MONEY, "const sign = cents < 0 ? '-' : ''", "const sign = ''"),
    ("negative sign after the symbol", MONEY, "return `${sign}${symbol}${units}.${rest}`", "return `${symbol}${sign}${units}.${rest}`"),
    ("unknown currency without a space", MONEY, "SYMBOLS[currency] ?? `${currency} `", "SYMBOLS[currency] ?? currency"),
    ("dollar sign wrong", MONEY, "USD: '$'", "USD: 'USD '"),
    ("default currency not euro", MONEY, "cents: number, currency = 'EUR'", "cents: number, currency = 'USD'"),
    ("units rounded instead of floored", MONEY, "Math.floor(abs / 100)", "Math.round(abs / 100)"),
    ("spaces not trimmed", MONEY, "AMOUNT.exec(text.trim())", "AMOUNT.exec(text)"),
    ("comma not accepted", MONEY, "(?:[.,](\\d{1,2}))", "(?:[.](\\d{1,2}))"),
    ("three decimals accepted", MONEY, "(\\d{1,2})", "(\\d{1,3})"),
    ("partial match accepted", MONEY, "/^(\\d+)(?:[.,](\\d{1,2}))?$/", "/^(\\d+)(?:[.,](\\d{1,2}))?/"),
    ("one-digit fraction read as cents", MONEY, FIXED_FRACTION, BUGGY_FRACTION),
    ("delay ignored", HOOK, "setTimeout(() => setSettled(value), delay)", "setTimeout(() => setSettled(value), 0)"),
    ("delay off by half", HOOK, "setTimeout(() => setSettled(value), delay)", "setTimeout(() => setSettled(value), delay / 2)"),
    ("wait not restarted", HOOK, "    return () => clearTimeout(timer)\n", ""),
    ("first value not returned", HOOK, "useState(value)", "useState(undefined as T)"),
    ("page_size not sent", API, "page, page_size: PAGE_SIZE }", "page }"),
    ("status=all sent", API, FIXED_STATUS, BUGGY_STATUS),
    ("status never sent", API, "        if (status !== 'all') params.status = status\n", ""),
    ("search not trimmed", API, "const text = search?.trim()", "const text = search"),
    ("blank search sent", API, "if (text) params.search = text", "if (text !== undefined) params.search = text"),
    ("detail path wrong", API, "query: (id) => `/invoices/${id}/`", "query: (id) => `/invoices/${id}`"),
    ("update sends PUT", API, "method: 'PATCH', body: changes", "method: 'PUT', body: changes"),
    ("update sends the id in the body", API, "query: ({ id, ...changes }) => ({ url: `/invoices/${id}/`, method: 'PATCH', body: changes })", "query: (changes) => ({ url: `/invoices/${changes.id}/`, method: 'PATCH', body: changes })"),
    ("update does not refresh the list", API, "invalidatesTags: (_result, _error, { id }) => [{ type: 'Invoice', id }, { type: 'Invoice', id: 'LIST' }],\n    }),\n    markPaid", "invalidatesTags: (_result, _error, { id }) => [{ type: 'Invoice', id }],\n    }),\n    markPaid"),
    ("pay sends camelCase", API, "body: { paid_on: paidOn }", "body: { paidOn }"),
    ("pay does not refresh the invoice", API, "invalidatesTags: (_result, _error, { id }) => [{ type: 'Invoice', id }, { type: 'Invoice', id: 'LIST' }],\n    }),\n  }),", "invalidatesTags: [{ type: 'Invoice', id: 'LIST' }],\n    }),\n  }),"),
    ("edit amount shown in cents", FORM, "useState(invoice ? centsToText(invoice.amount_cents) : '')", "useState(invoice ? String(invoice.amount_cents) : '')"),
    ("edit title wrong", FORM, "`Edit invoice ${invoice.number}`", "'Edit invoice'"),
    ("customer not required", FORM, "    if (!customer.trim()) found.customer = 'Enter the customer'\n", ""),
    ("blank customer accepted", FORM, "if (!customer.trim()) found.customer", "if (!customer) found.customer"),
    ("zero amount accepted", FORM, "cents === null || cents <= 0", "cents === null || cents < 0"),
    ("due date not required", FORM, "    if (!dueDate) found.due_date = 'Pick the due date'\n", ""),
    ("customer not trimmed", FORM, "{ customer: customer.trim(), amount_cents", "{ customer, amount_cents"),
    ("blank notes sent", FORM, "if (notes.trim()) input.notes = notes.trim()", "input.notes = notes.trim()"),
    ("notes not trimmed", FORM, "input.notes = notes.trim()", "input.notes = notes"),
    ("Save not disabled while saving", FORM, "    setSaving(true)\n", ""),
    ("done called on failure", FORM, "        setErrors({ form: 'Could not save the invoice' })\n", "        setErrors({ form: 'Could not save the invoice' })\n        onDone()\n"),
    ("done not called after saving", FORM, "      setSaving(false)\n      onDone()", "      setSaving(false)"),
    ("server field errors ignored", FORM, "      if (fieldErrors) {", "      if (false) {"),
    ("Save stays disabled after field errors", FORM, FIXED_SAVING, BUGGY_SAVING),
    ("cancel submits", FORM, "<button type=\"button\" onClick={onDone}>", "<button type=\"submit\">"),
]

DUE = "src/utils/dueLabel.ts"
AUTOSAVE = "src/hooks/useAutosave.ts"
LIST = "src/components/TaskList.tsx"

# Bug 1: one day overdue reads "Overdue by 1 days".
BUGGY_PLURAL = "  return `Overdue by ${-days} days`"
FIXED_PLURAL = "  return -days === 1 ? 'Overdue by 1 day' : `Overdue by ${-days} days`"
# Bug 2: "Only mine" ignores the status filter.
BUGGY_FILTER = ".filter((task) => (mine ? task.ownerId === user.id : status === 'all' || (status === 'done') === task.done))"
FIXED_FILTER = ".filter((task) => (!mine || task.ownerId === user.id) && (status === 'all' || (status === 'done') === task.done))"
# Bug 3: a pending change is dropped on unmount instead of saved.
BUGGY_UNMOUNT = """      mounted.current = false
      clearTimeout(timer.current)
    }"""
FIXED_UNMOUNT = """      mounted.current = false
      if (timer.current !== undefined) void flush()
    }"""
TASKS_FIXES = [(DUE, BUGGY_PLURAL, FIXED_PLURAL), (LIST, BUGGY_FILTER, FIXED_FILTER), (AUTOSAVE, BUGGY_UNMOUNT, FIXED_UNMOUNT)]

TASKS_MUTANTS = [
    ("no due date not handled", DUE, "  if (!dueDate) return 'No due date'\n", "  if (dueDate === null) return 'No due date'\n"),
    ("tomorrow shown as in 1 days", DUE, "  if (days === 1) return 'Due tomorrow'\n", ""),
    ("today off by one", DUE, "if (days === 0) return 'Due today'", "if (days === 0 || days === -1) return 'Due today'"),
    ("time of day counts", DUE, "localMidnight(now).getTime()", "now.getTime()"),
    ("days floored", DUE, "Math.round(", "Math.floor(-0.5 + "),
    ("singular day wrong", DUE, FIXED_PLURAL, BUGGY_PLURAL),
    ("future count off by one", DUE, "`Due in ${days} days`", "`Due in ${days - 1} days`"),
    ("first value saved", AUTOSAVE, "  const saved = useRef(value)", "  const saved = useRef<T | undefined>(undefined)"),
    ("equal value saved again", AUTOSAVE, "    if (next === saved.current) return\n", ""),
    ("wait not restarted", AUTOSAVE, "    clearTimeout(timer.current)\n    timer.current = setTimeout(flush, delay)", "    if (timer.current === undefined) timer.current = setTimeout(flush, delay)"),
    ("delay ignored", AUTOSAVE, "setTimeout(flush, delay)", "setTimeout(flush, 0)"),
    ("default delay wrong", AUTOSAVE, "delay = 1000) => {", "delay = 500) => {"),
    ("status not saving", AUTOSAVE, "    if (mounted.current) setStatus('saving')\n", ""),
    ("error reported as saved", AUTOSAVE, "      if (mounted.current) setStatus('error')", "      if (mounted.current) setStatus('saved')"),
    ("failed value marked saved", AUTOSAVE, "      await saveRef.current(next)\n      saved.current = next", "      saved.current = next\n      await saveRef.current(next)"),
    ("pending change dropped on unmount", AUTOSAVE, FIXED_UNMOUNT, BUGGY_UNMOUNT),
    ("unmount saves even without a change", AUTOSAVE, "      if (timer.current !== undefined) void flush()", "      void saveRef.current(latest.current)"),
    ("done tasks not last", LIST, "  if (a.done !== b.done) return a.done ? 1 : -1\n", ""),
    ("undated tasks first", LIST, "  if (!a.dueDate) return 1\n  if (!b.dueDate) return -1", "  if (!a.dueDate) return -1\n  if (!b.dueDate) return 1"),
    ("latest due first", LIST, "return a.dueDate < b.dueDate ? -1 : 1", "return a.dueDate < b.dueDate ? 1 : -1"),
    ("only mine ignored", LIST, FIXED_FILTER, ".filter((task) => status === 'all' || (status === 'done') === task.done)"),
    ("only mine drops the status", LIST, FIXED_FILTER, BUGGY_FILTER),
    ("open and done swapped", LIST, "(status === 'done') === task.done))", "(status === 'open') === task.done))"),
    ("pressed state wrong", LIST, "aria-pressed={status === value}", "aria-pressed={status === 'all'}"),
    ("summary counts total twice", LIST, "`${visible.length} of ${tasks.length} tasks`", "`${tasks.length} of ${tasks.length} tasks`"),
    ("empty message missing", LIST, "visible.length === 0 ? 'No tasks match'", "visible.length === -1 ? 'No tasks match'"),
    ("toggle sends the old state", LIST, "onToggle(task.id, event.target.checked)", "onToggle(task.id, task.done)"),
    ("members delete others' tasks", LIST, "(user.role === 'admin' || task.ownerId === user.id)", "(true)"),
    ("admins delete only their own", LIST, "(user.role === 'admin' || task.ownerId === user.id)", "(task.ownerId === user.id)"),
    ("delete without confirming", LIST, "<button type=\"button\" onClick={() => setConfirming(task.id)}>", "<button type=\"button\" onClick={() => onDelete(task.id)}>"),
    ("keep deletes", LIST, "<button type=\"button\" onClick={() => setConfirming(null)}>", "<button type=\"button\" onClick={() => onDelete(task.id)}>"),
    ("delete sends the owner", LIST, "onClick={() => onDelete(task.id)}>\n                    Delete", "onClick={() => onDelete(task.ownerId)}>\n                    Delete"),
]

# Change task: the due date becomes optional; a blank one is sent as due_date: null.
CHANGE_FIXES = [
    (FORM, "    if (!dueDate) found.due_date = 'Pick the due date'\n", ""),
    (FORM, "  due_date: string\n  notes?: string\n}\n\ntype Field", "  due_date: string | null\n  notes?: string\n}\n\ntype Field"),
    (FORM, "{ customer: customer.trim(), amount_cents: cents, due_date: dueDate }", "{ customer: customer.trim(), amount_cents: cents, due_date: dueDate || null }"),
]
CHANGE_MUTANTS = [
    ("blank due date sent as empty text", FORM, "due_date: dueDate || null }", "due_date: dueDate }"),
    ("due date dropped", FORM, "due_date: dueDate || null }", "due_date: null }"),
    ("customer not required", FORM, "    if (!customer.trim()) found.customer = 'Enter the customer'\n", ""),
    ("zero amount accepted", FORM, "cents === null || cents <= 0", "cents === null || cents < 0"),
    ("blank notes sent", FORM, "if (notes.trim()) input.notes = notes.trim()", "input.notes = notes.trim()"),
    ("Save stays disabled after field errors", FORM, FIXED_SAVING, BUGGY_SAVING),
    ("Save not disabled while saving", FORM, "    setSaving(true)\n", ""),
    ("cancel submits", FORM, "<button type=\"button\" onClick={onDone}>", "<button type=\"submit\">"),
]
CHANGE_FINAL = """import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'

import { InvoiceForm } from './InvoiceForm'

it('sends a blank due date as null, and a picked one as is', async () => {
  const onSubmit = vi.fn(() => Promise.resolve())
  const user = userEvent.setup()
  render(<InvoiceForm onSubmit={onSubmit} onDone={() => {}} />)
  await user.type(screen.getByLabelText('Customer'), 'Acme')
  await user.type(screen.getByLabelText('Amount'), '5')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(screen.queryByText('Pick the due date')).not.toBeInTheDocument()
  expect(onSubmit).toHaveBeenLastCalledWith({ customer: 'Acme', amount_cents: 500, due_date: null })
  await vi.waitFor(() => expect(screen.getByRole('button', { name: 'Save' })).toBeEnabled())
  await user.type(screen.getByLabelText('Due date'), '2026-05-01')
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(onSubmit).toHaveBeenLastCalledWith({ customer: 'Acme', amount_cents: 500, due_date: '2026-05-01' })
})

it('still requires the customer and the amount', async () => {
  const onSubmit = vi.fn(() => Promise.resolve())
  const user = userEvent.setup()
  render(<InvoiceForm onSubmit={onSubmit} onDone={() => {}} />)
  await user.click(screen.getByRole('button', { name: 'Save' }))
  expect(screen.getByText('Enter the customer')).toBeInTheDocument()
  expect(screen.getByText('Enter an amount above zero')).toBeInTheDocument()
  expect(onSubmit).not.toHaveBeenCalled()
})
"""

SPECS = {
    "billing": {
        "fixture": "billing",
        "fixes": BILLING_FIXES,
        "mutants": BILLING_MUTANTS,
        "untouched": [MONEY, HOOK, API, FORM],
        "reports": [
            ("Reports that one-decimal amounts are misread", [r"(?i)12[.,]5|one[- ]digit|single[- ]digit|one decimal|1205|pad"]),
            ("Reports that Save stays disabled after field errors", [r"(?i)disabled|saving", r"(?i)field error|server|reject|400"]),
            ("Reports that status=all is sent", [r"(?i)status", r"(?i)\ball\b"]),
        ],
    },
    "change": {
        "fixture": "change",
        "fixes": CHANGE_FIXES,
        "mutants": CHANGE_MUTANTS,
        "change": True,
        "target": FORM,
        "final_tests": {"src/components/final-due.test.tsx": CHANGE_FINAL},
        "min_tests": 22,
        "stale_label": "No test asserts the old required due date",
        "reports": [],
    },
    "tasks": {
        "fixture": "tasks",
        "fixes": TASKS_FIXES,
        "mutants": TASKS_MUTANTS,
        "untouched": [DUE, AUTOSAVE, LIST],
        "reports": [
            ("Reports the 1 days plural", [r"(?i)1 days|plural|singular"]),
            ("Reports that only mine ignores the status", [r"(?i)only mine|mine", r"(?i)status|filter|done|open"]),
            ("Reports that unmount drops the pending save", [r"(?i)unmount", r"(?i)pending|lost|drop|not saved|never saved|discard|cancel"]),
        ],
    },
}
