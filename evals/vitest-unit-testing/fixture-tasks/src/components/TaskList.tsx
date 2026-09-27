/**
 * The task list.
 *
 * - Shows each task's title, owner, and due label (dueLabel), open tasks with the earliest due date first and tasks
 *   without a due date last; done tasks after all open ones. Each task has a checkbox named after its title;
 *   ticking or unticking it calls `onToggle(id, done)`.
 * - "All", "Open", and "Done" (buttons; the chosen one is pressed) filter by status; "Only mine" keeps the current
 *   user's tasks. Both apply together. The summary reads "<shown> of <total> tasks"; when nothing matches it reads
 *   "No tasks match".
 * - A task's owner and admins see "Delete <title>". It asks "Delete <title>?" with "Delete" and "Keep"; "Delete" calls
 *   `onDelete(id)`, "Keep" closes the question. Members never see delete on others' tasks.
 */
import { useState } from 'react'

import { dueLabel } from '../utils/dueLabel'

export interface Task {
  id: number
  title: string
  ownerId: number
  ownerName: string
  dueDate: string | null
  done: boolean
}

export interface User {
  id: number
  role: 'member' | 'admin'
}

type Status = 'all' | 'open' | 'done'

interface Props {
  tasks: Task[]
  user: User
  onToggle: (id: number, done: boolean) => void
  onDelete: (id: number) => void
}

const order = (a: Task, b: Task) => {
  if (a.done !== b.done) return a.done ? 1 : -1
  if (a.dueDate === b.dueDate) return 0
  if (!a.dueDate) return 1
  if (!b.dueDate) return -1
  return a.dueDate < b.dueDate ? -1 : 1
}

export function TaskList({ tasks, user, onToggle, onDelete }: Props) {
  const [status, setStatus] = useState<Status>('all')
  const [mine, setMine] = useState(false)
  const [confirming, setConfirming] = useState<number | null>(null)

  const visible = tasks
    .filter((task) => (mine ? task.ownerId === user.id : status === 'all' || (status === 'done') === task.done))
    .sort(order)

  return (
    <section aria-label="Tasks">
      <div role="group" aria-label="Status">
        {(['all', 'open', 'done'] as const).map((value) => (
          <button key={value} type="button" aria-pressed={status === value} onClick={() => setStatus(value)}>
            {value[0].toUpperCase() + value.slice(1)}
          </button>
        ))}
      </div>
      <label>
        <input type="checkbox" checked={mine} onChange={(event) => setMine(event.target.checked)} /> Only mine
      </label>
      <p>{visible.length === 0 ? 'No tasks match' : `${visible.length} of ${tasks.length} tasks`}</p>
      <ul>
        {visible.map((task) => (
          <li key={task.id}>
            <label>
              <input type="checkbox" checked={task.done} onChange={(event) => onToggle(task.id, event.target.checked)} />
              {task.title}
            </label>
            <span> · {task.ownerName}</span>
            <span> · {dueLabel(task.dueDate)}</span>
            {(user.role === 'admin' || task.ownerId === user.id) &&
              (confirming === task.id ? (
                <span role="group" aria-label={`Delete ${task.title}?`}>
                  Delete {task.title}?
                  <button type="button" onClick={() => onDelete(task.id)}>
                    Delete
                  </button>
                  <button type="button" onClick={() => setConfirming(null)}>
                    Keep
                  </button>
                </span>
              ) : (
                <button type="button" onClick={() => setConfirming(task.id)}>
                  Delete {task.title}
                </button>
              ))}
          </li>
        ))}
      </ul>
    </section>
  )
}
