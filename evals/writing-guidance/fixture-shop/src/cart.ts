export type Line = { sku: string; qty: number; unitCents: number }

export function parseLine(raw: unknown): Line {
  const value = raw as any
  return { sku: String(value.sku), qty: Number(value.qty), unitCents: Number(value.unitCents) }
}

export const totalCents = (lines: Line[]): number => lines.reduce((sum, l) => sum + l.qty * l.unitCents, 0)
