import { useEffect, useState } from 'react'

/**
 * Returns `value` once it has stopped changing for `delay` milliseconds; until then, the last settled value.
 * The first render returns `value` right away. Each change restarts the wait, and nothing updates after unmount.
 */
export const useDebouncedValue = <T>(value: T, delay: number): T => {
  const [settled, setSettled] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(timer)
  }, [value, delay])

  return settled
}
