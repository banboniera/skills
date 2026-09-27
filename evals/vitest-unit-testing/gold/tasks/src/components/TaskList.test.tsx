import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { type Task, TaskList, type User } from './TaskList'

const me: User = { id: 1, role: 'member' }
const admin: User = { id: 9, role: 'admin' }
const task = (id: number, title: string, extra: Partial<Task> = {}): Task => ({
  id,
  title,
  ownerId: 1,
  ownerName: 'Me',
  dueDate: null,
  done: false,
  ...extra,
})
const tasks = [
  task(1, 'Write report', { dueDate: '2026-04-20' }),
  task(2, 'Call supplier', { ownerId: 2, ownerName: 'Ola', dueDate: '2026-04-12' }),
  task(3, 'Order parts', { done: true, dueDate: '2026-04-01' }),
  task(4, 'Plan trip'),
  task(5, 'Pay invoice', { ownerId: 2, ownerName: 'Ola', done: true }),
]

const setup = (user: User = me, list: Task[] = tasks) => {
  const onToggle = vi.fn()
  const onDelete = vi.fn()
  const events = userEvent.setup()
  render(<TaskList tasks={list} user={user} onToggle={onToggle} onDelete={onDelete} />)
  return { events, onToggle, onDelete }
}

const titles = () => screen.getAllByRole('listitem').map((item) => within(item).getAllByRole('checkbox')[0].closest('label')?.textContent)

afterEach(() => vi.useRealTimers())

describe('TaskList', () => {
  it('lists open tasks by due date, undated last, then done tasks', () => {
    setup()
    expect(titles()).toEqual(['Call supplier', 'Write report', 'Plan trip', 'Order parts', 'Pay invoice'])
    expect(screen.getByText('5 of 5 tasks')).toBeInTheDocument()
  })

  it('shows each task’s due label', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-04-12T10:00:00'))
    setup()
    const item = screen.getByRole('checkbox', { name: 'Call supplier' }).closest('li') as HTMLElement
    expect(item).toHaveTextContent('Due today')
    expect(screen.getByRole('checkbox', { name: 'Plan trip' }).closest('li')).toHaveTextContent('No due date')
  })

  it.each([
    ['Open', ['Call supplier', 'Write report', 'Plan trip']],
    ['Done', ['Order parts', 'Pay invoice']],
    ['All', ['Call supplier', 'Write report', 'Plan trip', 'Order parts', 'Pay invoice']],
  ])('filters by %s', async (button, expected) => {
    const { events } = setup()
    await events.click(screen.getByRole('button', { name: 'Open' }))
    await events.click(screen.getByRole('button', { name: button }))
    expect(screen.getByRole('button', { name: button })).toHaveAttribute('aria-pressed', 'true')
    expect(titles()).toEqual(expected)
    expect(screen.getByText(`${expected.length} of 5 tasks`)).toBeInTheDocument()
  })

  it('combines only mine with the status filter', async () => {
    const { events } = setup()
    await events.click(screen.getByRole('checkbox', { name: 'Only mine' }))
    expect(titles()).toEqual(['Write report', 'Plan trip', 'Order parts'])
    await events.click(screen.getByRole('button', { name: 'Done' }))
    expect(titles()).toEqual(['Order parts'])
    expect(screen.getByText('1 of 5 tasks')).toBeInTheDocument()
  })

  it('says when nothing matches', async () => {
    const { events } = setup(me, [task(2, 'Call supplier', { ownerId: 2 })])
    await events.click(screen.getByRole('checkbox', { name: 'Only mine' }))
    expect(screen.getByText('No tasks match')).toBeInTheDocument()
    expect(screen.queryByRole('listitem')).not.toBeInTheDocument()
  })

  it('reports ticking and unticking', async () => {
    const { events, onToggle } = setup()
    await events.click(screen.getByRole('checkbox', { name: 'Write report' }))
    expect(onToggle).toHaveBeenLastCalledWith(1, true)
    await events.click(screen.getByRole('checkbox', { name: 'Order parts' }))
    expect(onToggle).toHaveBeenLastCalledWith(3, false)
    expect(onToggle).toHaveBeenCalledTimes(2)
  })

  it('lets members delete only their own tasks', () => {
    setup(me)
    expect(screen.getByRole('button', { name: 'Delete Write report' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete Order parts' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete Call supplier' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Delete Pay invoice' })).not.toBeInTheDocument()
  })

  it('lets admins delete any task', () => {
    setup(admin)
    expect(screen.getAllByRole('button', { name: /^Delete / })).toHaveLength(5)
  })

  it('deletes after confirming', async () => {
    const { events, onDelete } = setup()
    await events.click(screen.getByRole('button', { name: 'Delete Order parts' }))
    const question = screen.getByRole('group', { name: 'Delete Order parts?' })
    expect(onDelete).not.toHaveBeenCalled()
    await events.click(within(question).getByRole('button', { name: 'Delete' }))
    expect(onDelete).toHaveBeenCalledExactlyOnceWith(3)
  })

  it('keeps the task when the user says keep', async () => {
    const { events, onDelete } = setup()
    await events.click(screen.getByRole('button', { name: 'Delete Write report' }))
    await events.click(within(screen.getByRole('group', { name: 'Delete Write report?' })).getByRole('button', { name: 'Keep' }))
    expect(screen.queryByRole('group', { name: 'Delete Write report?' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Delete Write report' })).toBeInTheDocument()
    expect(onDelete).not.toHaveBeenCalled()
  })
})
