import { appendFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, isAbsolute } from "node:path";
import { randomBytes, timingSafeEqual } from "node:crypto";
import { Budget, inputTokenCeiling, object, requestCostCeiling, UsageReader, type Admission,
  type BudgetTotals, type PricedModel } from "./budget";

export interface GatewayModel extends PricedModel { provider: string; id: string; api: string }
interface Router { route(request: Request, peer: string): Promise<Response>; close(): void }
interface ActiveRequest { controller: AbortController; done: Promise<void> }
interface Trial {
  id: string;
  models: ReadonlySet<string>;
  budget: Budget;
  usagePath: string;
  router: Router;
  active: Set<ActiveRequest>;
  revoked: boolean;
}
interface GatewayOptions {
  engineSecret: string;
  models: ReadonlyMap<string, GatewayModel>;
  router: (allowed: ReadonlySet<string>) => Router;
}

function authenticated(request: Request, secret: string): boolean {
  const actual = Buffer.from(request.headers.get("authorization") ?? "");
  const expected = Buffer.from(`Bearer ${secret}`);
  return actual.length === expected.length && timingSafeEqual(actual, expected);
}

function log(trial: Trial, record: Record<string, unknown>): void {
  try {
    appendFileSync(trial.usagePath, `${JSON.stringify({ time: new Date().toISOString(), ...record })}\n`, { mode: 0o600 });
  } catch (error) {
    // Accounting failure is fail-closed, not permission to spend unrecorded.
    trial.revoked = true;
    for (const active of trial.active) active.controller.abort();
    throw error;
  }
}

export function createGateway(options: GatewayOptions): {
  port: number; controlPort: number; close: () => Promise<void>;
} {
  const trials = new Map<string, Trial>();
  let closing = false;

  async function revoke(trial: Trial): Promise<BudgetTotals> {
    trial.revoked = true;
    for (const active of trial.active) active.controller.abort();
    await Promise.all([...trial.active].map(active => active.done));
    trial.router.close();
    const totals = trial.budget.totals();
    log(trial, { type: "revoked", ...totals });
    return totals;
  }

  const data = Bun.serve({
    hostname: "127.0.0.1", port: 0, idleTimeout: 0, maxRequestBodySize: 16 * 1024 * 1024,
    async fetch(request) {
      const path = new URL(request.url).pathname;
      if (path === "/healthz" && request.method === "GET") return Response.json({ ok: !closing });
      if (request.method !== "POST" || (path !== "/v1/pi/stream" && path !== "/v1/systemone")) {
        return Response.json({ error: "Not found" }, { status: 404 });
      }
      const authorization = request.headers.get("authorization") ?? "";
      const token = authorization.startsWith("Bearer ") ? authorization.slice(7) : "";
      const trial = trials.get(token);
      if (closing || !trial || trial.revoked) return Response.json({ error: "Unauthorized" }, { status: 401 });
      let body: Record<string, unknown> | undefined;
      try { body = object(await request.json()); }
      catch (error) {
        if (error instanceof SyntaxError) return Response.json({ error: "Invalid JSON" }, { status: 400 });
        throw error;
      }
      if (!body) return Response.json({ error: "Expected object" }, { status: 400 });
      const selector = path === "/v1/pi/stream" ? body.modelId ?? body.model : body.model;
      if (typeof selector !== "string" || !trial.models.has(selector)) {
        return Response.json({ error: "Model not allowed" }, { status: 403 });
      }
      const model = options.models.get(selector);
      if (!model) return Response.json({ error: "Model unavailable" }, { status: 404 });
      if (trial.revoked) return Response.json({ error: "Unauthorized" }, { status: 401 });
      const rawOptions = object(body.options) ?? {};
      // Unpriced tiers, model suffixes and user-injected headers can bypass a
      // catalog-price ceiling. They are not part of this gateway's contract.
      if (rawOptions.headers !== undefined || rawOptions.openrouterVariant !== undefined ||
          (rawOptions.serviceTier !== undefined && rawOptions.serviceTier !== "default")) {
        return Response.json({ error: "Unpriced inference options" }, { status: 400 });
      }
      const maxTokens = path === "/v1/pi/stream" ? rawOptions.maxTokens ?? model.maxTokens : model.maxTokens;
      if (typeof maxTokens !== "number") return Response.json({ error: "Invalid maxTokens" }, { status: 400 });
      let costCeiling: number;
      try {
        const longCache = (model.api === "anthropic-messages" || model.api === "bedrock-converse-stream") &&
          rawOptions.cacheRetention !== "short" && rawOptions.cacheRetention !== "none";
        costCeiling = requestCostCeiling(model, maxTokens, inputTokenCeiling(model, body), longCache);
      }
      catch (error) {
        if (error instanceof Error && (error.message === "Invalid token ceiling" || error.message === "Invalid cost")) {
          return Response.json({ error: "Invalid model price or token ceiling" }, { status: 400 });
        }
        throw error;
      }
      // Native judges can split questions into separate billed requests. Their
      // aggregate pending ceiling is informational, not money held from the cap.
      if (path === "/v1/systemone") {
        const questions = object(body.questions);
        const questionCount = questions ? Object.keys(questions).length : 0;
        if (questionCount === 0) return Response.json({ error: "Missing questions" }, { status: 400 });
        costCeiling *= questionCount;
      } else {
        const session = typeof rawOptions.sessionId === "string" ? rawOptions.sessionId : "default";
        const sessionId = `${trial.id}:${Bun.hash(session).toString(16)}`;
        body.modelId = selector;
        body.model = selector;
        body.options = { ...rawOptions, maxTokens, maxHttpAttempts: 1, sessionId, promptCacheKey: sessionId };
      }
      let lease: Admission;
      try { lease = trial.budget.admit(costCeiling); }
      catch (error) {
        if (error instanceof Error && (error.message === "Budget exhausted" ||
            error.message === "Trial concurrency limit reached" || error.message === "Unmeasured inference usage")) {
          return Response.json({ error: error.message }, { status: 429 });
        }
        throw error;
      }
      const controller = new AbortController();
      const signal = AbortSignal.any([request.signal, controller.signal]);
      const usage = new UsageReader(model);
      const { promise: done, resolve: complete } = Promise.withResolvers<void>();
      let cancelStream: (() => void) | undefined;
      const active = { controller, done };
      trial.active.add(active);
      let finished = false;
      const settle = () => {
        if (finished) return;
        finished = true;
        if (cancelStream) signal.removeEventListener("abort", cancelStream);
        lease.settle(usage.usage?.cost, usage.usage?.tokens ?? 0);
        trial.active.delete(active);
        complete();
        log(trial, { type: "request", model: selector, route: path,
          measured: usage.usage !== undefined, cost: usage.usage?.cost ?? null, costCeiling,
          tokens: usage.usage?.tokens ?? 0, inputTokens: usage.usage?.inputTokens ?? null,
          outputTokens: usage.usage?.outputTokens ?? null, cacheReadTokens: usage.usage?.cacheReadTokens ?? null,
          cacheWriteTokens: usage.usage?.cacheWriteTokens ?? null,
          cacheReadReported: usage.usage?.cacheReadReported ?? false, totals: trial.budget.totals() });
      };
      try {
        log(trial, { type: "request_start", model: selector, route: path });
        // No client bearer, forwarded headers or control secret enters the SDK.
        const response = await trial.router.route(new Request(`http://localhost${path}`, {
          method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(body), signal,
        }), "guidance-evals");
        if (!response.ok) {
          await response.body?.cancel();
          settle(); // Missing usage blocks later paid requests; no guessed debit.
          return Response.json({ error: "Upstream inference failed" }, { status: response.status });
        }
        if (!response.headers.get("content-type")?.includes("text/event-stream")) {
          const value: unknown = await response.json();
          usage.json(value, response.headers.get("x-litellm-response-cost"));
          settle();
          return Response.json(value);
        }
        if (!response.body) throw new Error("Missing upstream stream");
        const reader = response.body.getReader();
        const cancelled = async () => {
          try { await reader.cancel(); } finally { settle(); }
        };
        cancelStream = () => {
          void cancelled().catch(() => {
            // Cancellation is an API boundary too: prohibit reuse when the
            // upstream cannot be cancelled, without guessing billed usage.
            trial.revoked = true;
          });
        };
        signal.addEventListener("abort", cancelStream, { once: true });
        if (signal.aborted) await cancelled();
        const stream = new ReadableStream<Uint8Array>({
          async pull(output) {
            try {
              const chunk = await reader.read();
              if (chunk.done) {
                usage.end();
                settle();
                output.close();
              } else {
                usage.push(chunk.value);
                output.enqueue(chunk.value);
              }
            } catch {
              controller.abort();
              settle();
              output.error(new Error("Inference stream failed"));
            }
          },
          async cancel() { controller.abort(); await cancelled(); },
        });
        return new Response(stream, { headers: { "content-type": "text/event-stream", "cache-control": "no-store" } });
      } catch {
        const aborted = signal.aborted;
        controller.abort();
        settle();
        // This is the public API error boundary. Never echo SDK exceptions or
        // provider response bodies, which may contain credential material.
        return Response.json({ error: "Inference failed" }, { status: aborted ? 499 : 502 });
      }
    },
    error() { return Response.json({ error: "Dispatcher failure" }, { status: 500 }); },
  });

  let control: ReturnType<typeof Bun.serve>;
  try {
    control = Bun.serve({
      hostname: "127.0.0.1", port: 0, maxRequestBodySize: 64 * 1024,
      async fetch(request) {
        if (!authenticated(request, options.engineSecret)) return Response.json({ error: "Unauthorized" }, { status: 401 });
        const path = new URL(request.url).pathname;
        if (path === "/healthz" && request.method === "GET") return Response.json({ ok: !closing });
        if (closing || request.method !== "POST") return Response.json({ error: "Not found" }, { status: 404 });
        let body: Record<string, unknown> | undefined;
        try { body = object(await request.json()); }
        catch (error) {
          if (error instanceof SyntaxError) return Response.json({ error: "Invalid JSON" }, { status: 400 });
          throw error;
        }
        if (!body) return Response.json({ error: "Expected object" }, { status: 400 });
        if (path === "/register") {
          const { models, max_cost: maxCost, usage_path: usagePath } = body;
          if (!Array.isArray(models) || models.length === 0 ||
              !models.every((id): id is string => typeof id === "string" && options.models.has(id)) ||
              typeof maxCost !== "number" || !Number.isFinite(maxCost) || maxCost < 0 ||
              typeof usagePath !== "string" || !isAbsolute(usagePath)) {
            return Response.json({ error: "Invalid trial policy" }, { status: 400 });
          }
          mkdirSync(dirname(usagePath), { recursive: true, mode: 0o700 });
          // Never append a new trial to an earlier trial's accounting record.
          writeFileSync(usagePath, "", { flag: "wx", mode: 0o600 });
          const allowed = new Set(models);
          const trial: Trial = { id: crypto.randomUUID(), models: allowed, budget: new Budget(maxCost),
            usagePath, router: options.router(allowed), active: new Set(), revoked: false };
          const token = randomBytes(32).toString("hex");
          log(trial, { type: "registered", models, max_cost: maxCost });
          trials.set(token, trial);
          return Response.json({ token });
        }
        if (path === "/revoke") {
          if (typeof body.token !== "string") return Response.json({ error: "Missing trial token" }, { status: 400 });
          const trial = trials.get(body.token);
          if (!trial) return Response.json({ error: "Unknown trial token" }, { status: 404 });
          const totals = await revoke(trial);
          trials.delete(body.token);
          return Response.json(totals);
        }
        return Response.json({ error: "Not found" }, { status: 404 });
      },
      error() { return Response.json({ error: "Control operation failed" }, { status: 500 }); },
    });
  } catch (error) {
    void data.stop(true);
    throw error;
  }
  return {
    port: data.port, controlPort: control.port,
    async close() {
      closing = true;
      await Promise.all([...trials.values()].map(revoke));
      trials.clear();
      await Promise.all([data.stop(true), control.stop(true)]);
    },
  };
}
