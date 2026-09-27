import { describe, expect, it } from 'vitest'

import { formatMoney, parseAmount } from './money'

describe('formatMoney', () => {
  it.each([
    [0, 'EUR', '€0.00'],
    [5, 'EUR', '€0.05'],
    [99, 'EUR', '€0.99'],
    [100, 'EUR', '€1.00'],
    [123456, 'EUR', '€1,234.56'],
    [100000000, 'EUR', '€1,000,000.00'],
    [99999, 'EUR', '€999.99'],
    [-123456, 'EUR', '-€1,234.56'],
    [-5, 'EUR', '-€0.05'],
    [1250, 'USD', '$12.50'],
    [500, 'PLN', 'PLN 5.00'],
  ])('formats %i %s as %s', (cents, currency, expected) => {
    expect(formatMoney(cents, currency)).toBe(expected)
  })

  it('uses euros by default', () => {
    expect(formatMoney(1250)).toBe('€12.50')
  })
})

describe('parseAmount', () => {
  it.each([
    ['12', 1200],
    ['12.5', 1250],
    ['12.50', 1250],
    ['12,05', 1205],
    ['12,5', 1250],
    ['0.99', 99],
    ['0', 0],
    ['  7.10 ', 710],
    ['1000', 100000],
  ])('reads %j as %i cents', (text, cents) => {
    expect(parseAmount(text)).toBe(cents)
  })

  it.each(['', '   ', 'abc', '12.345', '-5', '+5', '1,234.50', '12.', '.5', '12 50', '1e3'])('rejects %j', (text) => {
    expect(parseAmount(text)).toBeNull()
  })
})
