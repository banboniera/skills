/** Pure, synchronous measured-spend ledger: admission never waits on settlement. */
export interface PricedModel {
  contextWindow: number;
  maxTokens: number;
  cost: { input: number; output: number; cacheRead: number; cacheWrite: number };
}

function money(value: number): number {
  if (!Number.isFinite(value) || value < 0) throw new Error("Invalid cost");
  return value;
}

// This is a byte upper bound for text, not a chars/4 token estimate. The
// allowance covers provider-injected system/tool templates and per-container
// role/schema framing that is not present in the native request JSON.
const PROTOCOL_BASE_TOKENS = 32_768;
const PROTOCOL_CONTAINER_TOKENS = 256;

export function inputTokenCeiling(model: PricedModel, payload: unknown): number {
  const serialized = JSON.stringify(payload);
  if (serialized === undefined) throw new Error("Invalid inference payload");
  const pending: unknown[] = [payload];
  let containers = 0;
  while (pending.length > 0) {
    const current = pending.pop();
    if (Array.isArray(current)) {
      containers++;
      for (const value of current) pending.push(value);
      continue;
    }
    const record = object(current);
    if (!record) continue;
    containers++;
    // Compressed media and provider-side caches can expand beyond their wire
    // bytes. Do not pretend a text tokenizer bounds those inputs.
    if (record.type === "image" || record.type === "audio" || record.type === "video" ||
        record.type === "document" || record.type === "file" ||
        record.images !== undefined || record.assets !== undefined ||
        record.cachedContent !== undefined || record.userProfileId !== undefined ||
        record.anthropicCompaction !== undefined ||
        (typeof record.mimeType === "string" && !record.mimeType.startsWith("text/"))) {
      return model.contextWindow;
    }
    for (const key in record) {
      if (Object.hasOwn(record, key)) pending.push(record[key]);
    }
  }
  return Math.min(model.contextWindow,
    Buffer.byteLength(serialized, "utf8") + PROTOCOL_BASE_TOKENS + containers * PROTOCOL_CONTAINER_TOKENS);
}

export function requestCostCeiling(model: PricedModel, maxTokens: number, inputTokens = model.contextWindow, longCache = false): number {
  if (!Number.isSafeInteger(model.maxTokens) || model.maxTokens < 1 ||
      !Number.isSafeInteger(maxTokens) || maxTokens < 1 || maxTokens > model.maxTokens ||
      !Number.isSafeInteger(model.contextWindow) || model.contextWindow < 1 ||
      !Number.isSafeInteger(inputTokens) || inputTokens < 0 || inputTokens > model.contextWindow) {
    throw new Error("Invalid token ceiling");
  }
  // Informational bound only, never financial admission. Output limits are
  // enforced on the wire and opaque inputs use the model's context bound.
  const inputRate = Math.max(money(model.cost.input), money(model.cost.cacheRead), money(model.cost.cacheWrite),
    longCache ? money(model.cost.input) * 2 : 0);
  return money((inputTokens * inputRate + maxTokens * money(model.cost.output)) / 1_000_000);
}

const MAX_CONCURRENT_REQUESTS_PER_TRIAL = 8;

export interface Admission {
  settle(actual: number | undefined, tokens: number): void;
}

export interface BudgetTotals {
  cost: number;
  tokens: number;
  requests: number;
  pending: number;
  pendingCostCeiling: number;
  overshoot: number;
  unmeasured: number;
}

export class Budget {
  private spent = 0;
  private pending = new Map<symbol, number>();
  private tokens = 0;
  private requests = 0;
  private unmeasured = 0;
  constructor(private readonly limit: number) { money(limit); }

  admit(costCeiling: number): Admission {
    money(costCeiling);
    if (this.spent >= this.limit) throw new Error("Budget exhausted");
    if (this.unmeasured > 0 && costCeiling > 0) throw new Error("Unmeasured inference usage");
    if (this.pending.size >= MAX_CONCURRENT_REQUESTS_PER_TRIAL) throw new Error("Trial concurrency limit reached");
    const id = Symbol();
    this.pending.set(id, costCeiling);
    let settled = false;
    return { settle: (actual, tokens) => {
      if (settled) return;
      if (actual !== undefined) money(actual);
      if (!Number.isSafeInteger(tokens) || tokens < 0) throw new Error("Invalid usage");
      settled = true;
      this.pending.delete(id);
      if (actual === undefined) this.unmeasured++;
      else this.spent += actual;
      this.tokens += tokens;
      this.requests++;
    } };
  }

  totals(): BudgetTotals {
    let pendingCostCeiling = 0;
    for (const cost of this.pending.values()) pendingCostCeiling += cost;
    return { cost: this.spent, tokens: this.tokens, requests: this.requests, pending: this.pending.size,
      pendingCostCeiling, overshoot: Math.max(0, this.spent - this.limit), unmeasured: this.unmeasured };
  }
}

export function object(value: unknown): Record<string, unknown> | undefined {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? value as Record<string, unknown> : undefined;
}

function nonnegative(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : undefined;
}

/** Reads only final upstream usage; never stores content, prompts or headers. */
export class UsageReader {
  usage: { cost: number; tokens: number; inputTokens: number; outputTokens: number;
    cacheReadTokens: number; cacheWriteTokens: number; cacheReadReported: boolean } | undefined;
  private decoder = new TextDecoder();
  private pending = "";
  constructor(private readonly model: PricedModel) {}

  json(value: unknown, headerCost?: string | null): void {
    const envelope = object(value);
    const message = object(envelope?.message) ?? envelope;
    const usage = object(message?.usage);
    if (!usage) return;
    const input = nonnegative(usage.input ?? usage.input_tokens);
    const output = nonnegative(usage.output ?? usage.output_tokens);
    if (input === undefined || output === undefined) return;
    const cacheRead = nonnegative(usage.cacheRead) ?? 0;
    const cacheWrite = nonnegative(usage.cacheWrite) ?? 0;
    const reported = nonnegative(object(usage.cost)?.total ?? usage.cost);
    const fromHeader = headerCost === undefined || headerCost === null ? undefined : nonnegative(Number(headerCost));
    const priced = (input * this.model.cost.input + output * this.model.cost.output +
      cacheRead * this.model.cost.cacheRead + cacheWrite * this.model.cost.cacheWrite) / 1_000_000;
    const cost = Math.max(reported ?? 0, fromHeader ?? 0, reported === undefined && fromHeader === undefined ? priced : 0);
    const tokens = nonnegative(usage.totalTokens) ?? input + output + cacheRead + cacheWrite;
    if (!Number.isSafeInteger(tokens) || !Number.isFinite(cost)) return;
    this.usage = { cost, tokens, inputTokens: input, outputTokens: output,
      cacheReadTokens: cacheRead, cacheWriteTokens: cacheWrite,
      cacheReadReported: nonnegative(usage.cacheRead) !== undefined };
  }

  push(chunk: Uint8Array): void {
    this.pending += this.decoder.decode(chunk, { stream: true });
    this.lines();
  }

  end(): void {
    this.pending += this.decoder.decode();
    this.lines();
    if (this.pending) this.line(this.pending);
    this.pending = "";
  }

  private lines(): void {
    let newline: number;
    while ((newline = this.pending.indexOf("\n")) !== -1) {
      this.line(this.pending.slice(0, newline).trimEnd());
      this.pending = this.pending.slice(newline + 1);
    }
    // A malformed upstream cannot retain an unbounded unterminated SSE line.
    if (this.pending.length > 16 * 1024 * 1024) throw new Error("Oversized stream event");
  }

  private line(line: string): void {
    if (!line.startsWith("data:")) return;
    const data = line.slice(5).trimStart();
    if (data === "[DONE]") return;
    let event: Record<string, unknown> | undefined;
    try {
      event = object(JSON.parse(data));
    } catch (error) {
      if (error instanceof SyntaxError) throw new Error("Malformed upstream stream event");
      throw error;
    }
    if (event?.type === "done") this.json({ message: event.message });
    if (event?.type === "error") this.json({ message: event.error });
  }
}
