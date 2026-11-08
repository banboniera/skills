import { describe, expect, test } from "bun:test";
import { Budget, inputTokenCeiling, requestCostCeiling, UsageReader } from "./budget";

const paid = {
  contextWindow: 1000, maxTokens: 100,
  cost: { input: 1, output: 2, cacheRead: 0.1, cacheWrite: 1.5 },
};

describe("measured-spend budget", () => {
  test("Opus requests continue under a 1.50 measured-spend cap despite larger theoretical ceilings", () => {
    const opus = { contextWindow: 1_000_000, maxTokens: 128_000,
      cost: { input: 5, output: 25, cacheRead: 0.5, cacheWrite: 6.25 } };
    const budget = new Budget(1.5);
    const ceiling = requestCostCeiling(opus, 128_000);
    expect(ceiling).toBe(9.45);
    budget.admit(ceiling).settle(0.0017, 10);
    budget.admit(ceiling).settle(0.0017, 10);
    budget.admit(ceiling).settle(1.4966, 10);
    expect(budget.totals().cost).toBeCloseTo(1.5, 12);
    expect(() => budget.admit(ceiling)).toThrow("Budget exhausted");
  });
  test("informational ceilings include long-cache rates and validate token bounds", () => {
    expect(requestCostCeiling(paid, 50, 1000, true)).toBeCloseTo(0.0021, 12);
    for (const maxTokens of [0, 101, NaN]) expect(() => requestCostCeiling(paid, maxTokens)).toThrow();
    for (const input of [-1, 1001]) expect(() => requestCostCeiling(paid, 50, input)).toThrow();
  });
  test("byte ceilings count UTF-8 and structural framing, not characters divided by four", () => {
    const model = { ...paid, contextWindow: 1_000_000 };
    const plain = inputTokenCeiling(model, { text: "a".repeat(100) });
    const unicode = inputTokenCeiling(model, { text: "界".repeat(100) });
    expect(unicode - plain).toBe(200);
    expect(inputTokenCeiling(paid, { text: "small" })).toBe(1000);
  });
  test("images and external cached content retain the full-context safety bound", () => {
    const model = { ...paid, contextWindow: 1_000_000 };
    expect(inputTokenCeiling(model, { context: { messages: [{ type: "image", data: "small-image" }] } })).toBe(1_000_000);
    expect(inputTokenCeiling(model, { options: { cachedContent: "opaque-provider-cache" } })).toBe(1_000_000);
    expect(inputTokenCeiling(model, { images: [{ data: "base64" }] })).toBe(1_000_000);
  });
  test("eight concurrent requests may finish over cap but a ninth cannot enter", () => {
    const budget = new Budget(1.5);
    const leases = Array.from({ length: 8 }, () => budget.admit(9.45));
    expect(() => budget.admit(9.45)).toThrow("Trial concurrency limit reached");
    expect(budget.totals()).toMatchObject({ cost: 0, tokens: 0, requests: 0,
      pending: 8, overshoot: 0, unmeasured: 0 });
    expect(budget.totals().pendingCostCeiling).toBeCloseTo(75.6, 12);
    leases[0]?.settle(1.5, 10);
    expect(() => budget.admit(9.45)).toThrow("Budget exhausted");
    for (const lease of leases.slice(1)) lease.settle(0.1, 10);
    expect(budget.totals().cost).toBeCloseTo(2.2, 12);
    expect(budget.totals().overshoot).toBeCloseTo(0.7, 12);
    expect(budget.totals()).toMatchObject({ pending: 0, pendingCostCeiling: 0, requests: 8, tokens: 80 });
  });
  test("settlement is idempotent and releases a concurrency slot", () => {
    const budget = new Budget(1.5);
    const lease = budget.admit(9.45);
    lease.settle(0.0017, 12);
    lease.settle(9, 99);
    expect(budget.totals()).toEqual({ cost: 0.0017, tokens: 12, requests: 1,
      pending: 0, pendingCostCeiling: 0, overshoot: 0, unmeasured: 0 });
    budget.admit(9.45).settle(0.0017, 12);
    expect(budget.totals().requests).toBe(2);
  });
  test("unmeasured usage blocks paid admissions without guessing actual cost", () => {
    const budget = new Budget(1.5);
    budget.admit(9.45).settle(0.0017, 12);
    budget.admit(9.45).settle(undefined, 0);
    expect(budget.totals()).toEqual({ cost: 0.0017, tokens: 12, requests: 2,
      pending: 0, pendingCostCeiling: 0, overshoot: 0, unmeasured: 1 });
    expect(() => budget.admit(9.45)).toThrow("Unmeasured inference usage");
    budget.admit(0).settle(0, 1);
  });
  test("zero-price models run under a positive cap without manufactured charges", () => {
    const budget = new Budget(0.05);
    for (let i = 0; i < 100; i++) budget.admit(0).settle(0, 9);
    expect(budget.totals()).toMatchObject({ cost: 0, tokens: 900, requests: 100, pending: 0 });
  });
  test("invalid money and usage cannot corrupt the ledger", () => {
    for (const value of [-1, Infinity, NaN]) {
      expect(() => new Budget(value)).toThrow();
      expect(() => new Budget(1).admit(value)).toThrow();
      const budget = new Budget(1);
      const lease = budget.admit(9);
      expect(() => lease.settle(value, 1)).toThrow();
      lease.settle(undefined, 0);
      expect(budget.totals()).toMatchObject({ cost: 0, unmeasured: 1, pending: 0 });
    }
    const lease = new Budget(1).admit(9);
    expect(() => lease.settle(0, -1)).toThrow();
    lease.settle(0, 1);
  });
});

describe("trusted usage extraction", () => {
  test("pi-native completion counts the final message only, not repeated partials", () => {
    const reader = new UsageReader(paid);
    const bytes = new TextEncoder().encode([
      'data: {"type":"text_delta","partial":{"usage":{"input":999,"output":999}}}\n\n',
      'data: {"type":"done","message":{"usage":{"input":10,"output":5,"cacheRead":2,"cacheWrite":3,"totalTokens":20,"cost":{"total":0.002}}}}\n\n',
      'data: [DONE]\n\n',
    ].join(""));
    for (let i = 0; i < bytes.length; i += 7) reader.push(bytes.slice(i, i + 7));
    reader.end();
    expect(reader.usage).toMatchObject({ cost: 0.002, tokens: 20 });
  });
  test("judge JSON uses catalog pricing when upstream omits cost", () => {
    const reader = new UsageReader(paid);
    reader.json({ usage: { input_tokens: 10, output_tokens: 5 } });
    expect(reader.usage?.cost).toBeCloseTo(0.00002, 12);
    expect(reader.usage?.tokens).toBe(15);
  });
  test("incomplete streams do not turn into a zero-cost success", () => {
    const reader = new UsageReader(paid);
    reader.push(new TextEncoder().encode('data: {"type":"text_delta"}\n\n'));
    reader.end();
    expect(reader.usage).toBeUndefined();
  });
  test("stream errors retain their reported billed usage", () => {
    const reader = new UsageReader(paid);
    reader.push(new TextEncoder().encode('data: {"type":"error","error":{"usage":{"input":10,"output":0,"cost":{"total":0.001}}}}\n\n'));
    reader.end();
    expect(reader.usage).toMatchObject({ cost: 0.001, tokens: 10 });
  });
});

test("usage preserves cache-read evidence separately from input and absent reporting", () => {
  const reader = new UsageReader(paid);
  reader.json({ usage: { input: 10, output: 5, cacheRead: 100, cacheWrite: 2, cost: 0 } });
  expect(reader.usage).toMatchObject({ inputTokens: 10, outputTokens: 5,
    cacheReadTokens: 100, cacheWriteTokens: 2, cacheReadReported: true });
  reader.json({ usage: { input: 10, output: 5, cost: 0 } });
  expect(reader.usage).toMatchObject({ inputTokens: 10, cacheReadTokens: 0, cacheReadReported: false });
});
