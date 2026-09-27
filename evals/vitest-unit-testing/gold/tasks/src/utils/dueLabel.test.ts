import { describe, expect, it } from 'vitest'

import { dueLabel } from './dueLabel'

const at = (text: string) => new Date(text)

describe('dueLabel', () => {
  it.each([
    ['2026-04-10', 'Due today'],
    ['2026-04-11', 'Due tomorrow'],
    ['2026-04-12', 'Due in 2 days'],
    ['2026-05-10', 'Due in 30 days'],
    ['2026-04-09', 'Overdue by 1 day'],
    ['2026-04-08', 'Overdue by 2 days'],
    ['2025-04-10', 'Overdue by 365 days'],
  ])('labels %s as %j on 2026-04-10', (due, label) => {
    expect(dueLabel(due, at('2026-04-10T12:00:00'))).toBe(label)
  })

  it.each(['2026-04-10T00:01:00', '2026-04-10T23:59:00'])('ignores the time of day (%s)', (now) => {
    expect(dueLabel('2026-04-10', at(now))).toBe('Due today')
    expect(dueLabel('2026-04-11', at(now))).toBe('Due tomorrow')
    expect(dueLabel('2026-04-09', at(now))).toBe('Overdue by 1 day')
  })

  it('counts calendar days across a month end', () => {
    expect(dueLabel('2026-03-01', at('2026-02-28T09:00:00'))).toBe('Due tomorrow')
  })

  it.each([null, ''])('has no due date for %j', (due) => {
    expect(dueLabel(due, at('2026-04-10T12:00:00'))).toBe('No due date')
  })
})
