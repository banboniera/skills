import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { useAutosave } from './useAutosave'

const setup = (save = vi.fn(() => Promise.resolve())) => {
  const hook = renderHook(({ value }) => useAutosave(value, save, 1000), { initialProps: { value: 'a' } })
  return { ...hook, save }
}

describe('useAutosave', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('never saves the first value', async () => {
    const { save, result } = setup()
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(save).not.toHaveBeenCalled()
    expect(result.current.status).toBe('idle')
  })

  it('saves a change once it has been still for the delay', async () => {
    const { save, rerender, result } = setup()
    rerender({ value: 'b' })
    await act(() => vi.advanceTimersByTimeAsync(999))
    expect(save).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(save).toHaveBeenCalledExactlyOnceWith('b')
    expect(result.current.status).toBe('saved')
  })

  it('waits one second by default', async () => {
    const save = vi.fn(() => Promise.resolve())
    const { rerender } = renderHook(({ value }) => useAutosave(value, save), { initialProps: { value: 'a' } })
    rerender({ value: 'b' })
    await act(() => vi.advanceTimersByTimeAsync(999))
    expect(save).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(1))
    expect(save).toHaveBeenCalledExactlyOnceWith('b')
  })

  it('restarts the wait on each change and saves only the last value', async () => {
    const { save, rerender } = setup()
    rerender({ value: 'b' })
    await act(() => vi.advanceTimersByTimeAsync(600))
    rerender({ value: 'c' })
    await act(() => vi.advanceTimersByTimeAsync(600))
    expect(save).not.toHaveBeenCalled()
    await act(() => vi.advanceTimersByTimeAsync(400))
    expect(save).toHaveBeenCalledExactlyOnceWith('c')
  })

  it('does not save a value equal to the last one saved', async () => {
    const { save, rerender } = setup()
    rerender({ value: 'b' })
    await act(() => vi.advanceTimersByTimeAsync(1000))
    rerender({ value: 'c' })
    rerender({ value: 'b' })
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(save).toHaveBeenCalledOnce()
  })

  it('reports saving while the save runs', async () => {
    let finish!: () => void
    const save = vi.fn(() => new Promise<void>((resolve) => (finish = resolve)))
    const { rerender, result } = setup(save)
    rerender({ value: 'b' })
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(result.current.status).toBe('saving')
    await act(async () => finish())
    expect(result.current.status).toBe('saved')
  })

  it('reports an error and retries the value on flush', async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
    const { rerender, result } = setup(save)
    rerender({ value: 'b' })
    await act(() => vi.advanceTimersByTimeAsync(1000))
    expect(result.current.status).toBe('error')
    await act(() => result.current.flush())
    expect(save).toHaveBeenCalledTimes(2)
    expect(save).toHaveBeenLastCalledWith('b')
    expect(result.current.status).toBe('saved')
  })

  it('flush saves a pending change right away, once', async () => {
    const { save, rerender, result } = setup()
    rerender({ value: 'b' })
    await act(() => result.current.flush())
    expect(save).toHaveBeenCalledExactlyOnceWith('b')
    await act(() => vi.advanceTimersByTimeAsync(5000))
    expect(save).toHaveBeenCalledOnce()
  })

  it('saves a pending change on unmount', () => {
    const { save, rerender, unmount } = setup()
    rerender({ value: 'b' })
    unmount()
    expect(save).toHaveBeenCalledExactlyOnceWith('b')
  })

  it('saves nothing on unmount when nothing is pending', async () => {
    const { save, rerender, unmount } = setup()
    rerender({ value: 'b' })
    await act(() => vi.advanceTimersByTimeAsync(1000))
    unmount()
    expect(save).toHaveBeenCalledOnce()
  })
})
