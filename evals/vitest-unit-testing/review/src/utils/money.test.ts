import { describe, expect, it } from 'vitest'

import { formatMoney, parseAmount } from './money'

describe('money', () => {
  it('formats money', () => {
    expect(formatMoney(123456)).toContain('1,234')
    expect(formatMoney(0)).toBe('€0.00')
  })

  it('parses amounts', () => {
    expect(parseAmount('12')).toBe(1200)
    expect(parseAmount('12.50')).toBe(1250)
  })
})
