import { renderHook, waitFor } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import { useDebouncedValue } from './useDebouncedValue'

describe('useDebouncedValue', () => {
  it('updates after the delay', async () => {
    const { result, rerender } = renderHook(({ value }) => useDebouncedValue(value, 300), { initialProps: { value: 'a' } })
    rerender({ value: 'b' })
    await new Promise((resolve) => setTimeout(resolve, 350))
    await waitFor(() => expect(result.current).toBe('b'))
  })
})
