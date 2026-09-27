/**
 * The label shown next to a task's due date, counted in whole calendar days in the user's local time zone.
 *
 * dueLabel(dueDate, now = new Date()), with dueDate as "YYYY-MM-DD":
 * - due today: "Due today"; due tomorrow: "Due tomorrow"; later: "Due in N days"
 * - past: "Overdue by 1 day", "Overdue by N days"
 * - no due date (null or ""): "No due date"
 * The time of day of `now` never matters: at 00:01 and at 23:59 the same date gives the same label.
 */
const DAY = 24 * 60 * 60 * 1000

const localMidnight = (date: Date) => new Date(date.getFullYear(), date.getMonth(), date.getDate())

const parseDay = (text: string) => {
  const [year, month, day] = text.split('-').map(Number)
  return new Date(year, month - 1, day)
}

export const dueLabel = (dueDate: string | null, now = new Date()): string => {
  if (!dueDate) return 'No due date'
  const days = Math.round((parseDay(dueDate).getTime() - localMidnight(now).getTime()) / DAY)
  if (days === 0) return 'Due today'
  if (days === 1) return 'Due tomorrow'
  if (days > 1) return `Due in ${days} days`
  return `Overdue by ${-days} days`
}
