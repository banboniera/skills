/**
 * Money is handled in integer cents.
 *
 * formatMoney(cents, currency = 'EUR'): the symbol (€ for EUR, $ for USD, otherwise the code and a space, e.g. "PLN 5.00"),
 * then the whole units with a comma between each group of three digits, a dot, and exactly two digits of cents.
 * Negative amounts start with a minus sign before the symbol: -123456 → "-€1,234.56".
 *
 * parseAmount(text): what a user typed into an amount field, in cents, or null when it is not an amount.
 * Surrounding spaces are ignored; the decimal separator may be a dot or a comma; at most two decimals;
 * no thousands separators and no sign. "12" → 1200, "12.5" → 1250, "12,05" → 1205, "0.99" → 99.
 * Empty text, letters, more than two decimals, and negative numbers give null.
 */
const SYMBOLS: Record<string, string> = { EUR: '€', USD: '$' }

export const formatMoney = (cents: number, currency = 'EUR'): string => {
  const symbol = SYMBOLS[currency] ?? `${currency} `
  const sign = cents < 0 ? '-' : ''
  const abs = Math.abs(cents)
  const units = Math.floor(abs / 100)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  const rest = String(abs % 100).padStart(2, '0')
  return `${sign}${symbol}${units}.${rest}`
}

const AMOUNT = /^(\d+)(?:[.,](\d{1,2}))?$/

export const parseAmount = (text: string): number | null => {
  const match = AMOUNT.exec(text.trim())
  if (!match) return null
  const [, whole, fraction = ''] = match
  return Number(whole) * 100 + Number(fraction || '0')
}
