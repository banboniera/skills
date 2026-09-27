import { useCallback, useEffect, useRef, useState } from 'react'

export type AutosaveStatus = 'idle' | 'saving' | 'saved' | 'error'

/**
 * Saves `value` with `save` once it has stayed unchanged for `delay` milliseconds (default 1000).
 *
 * - The first value is never saved, nor a value equal (===) to the last one saved or first seen.
 * - Each change restarts the wait. `flush()` saves a pending change right away.
 * - `status` is "saving" while `save` runs, then "saved", or "error" when it rejects; a failed value is saved
 *   again on the next change or flush.
 * - On unmount, a pending change is saved right away, so nothing typed is lost.
 */
export const useAutosave = <T>(value: T, save: (value: T) => Promise<unknown>, delay = 1000) => {
  const [status, setStatus] = useState<AutosaveStatus>('idle')
  const saved = useRef(value)
  const latest = useRef(value)
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const mounted = useRef(true)
  const saveRef = useRef(save)
  saveRef.current = save
  latest.current = value

  const flush = useCallback(async () => {
    clearTimeout(timer.current)
    timer.current = undefined
    const next = latest.current
    if (next === saved.current) return
    if (mounted.current) setStatus('saving')
    try {
      await saveRef.current(next)
      saved.current = next
      if (mounted.current) setStatus('saved')
    } catch {
      if (mounted.current) setStatus('error')
    }
  }, [])

  useEffect(() => {
    if (value === saved.current) return
    clearTimeout(timer.current)
    timer.current = setTimeout(flush, delay)
  }, [value, delay, flush])

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      clearTimeout(timer.current)
    }
  }, [])

  return { status, flush }
}
