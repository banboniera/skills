import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { vi } from 'vitest'

import { useDebouncedValue } from './useDebouncedValue'

describe('useDebouncedValue', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('returns the first value right away', () => {
    const { result } = renderHook(() => useDebouncedValue('a', 300))
    expect(result.current).toBe('a')
  })

  it('settles on a new value only after the delay', () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 300), { initialProps: { value: 'a' } })
    rerender({ value: 'b' })
    act(() => vi.advanceTimersByTime(299))
    expect(result.current).toBe('a')
    act(() => vi.advanceTimersByTime(1))
    expect(result.current).toBe('b')
  })

  it('restarts the wait on each change and keeps only the last value', () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 300), { initialProps: { value: 'a' } })
    rerender({ value: 'b' })
    act(() => vi.advanceTimersByTime(200))
    rerender({ value: 'c' })
    act(() => vi.advanceTimersByTime(200))
    expect(result.current).toBe('a')
    act(() => vi.advanceTimersByTime(100))
    expect(result.current).toBe('c')
  })

  it('schedules nothing after unmount', () => {
    const { rerender, unmount } = renderHook(({ value }) => useDebouncedValue(value, 300), { initialProps: { value: 'a' } })
    rerender({ value: 'b' })
    unmount()
    expect(vi.getTimerCount()).toBe(0)
  })
})
