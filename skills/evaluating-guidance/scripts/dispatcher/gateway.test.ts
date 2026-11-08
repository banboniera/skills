import { expect, test } from "bun:test";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { createGateway } from "./gateway";

// An in-memory inference boundary keeps these tests off host auth/network.
const model = { provider: "test", id: "free", api: "test", contextWindow: 1000, maxTokens: 100,
  cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 } };

test("control secret, inference bearer and model allowlist are separate authorities", async () => {
  const root = mkdtempSync(join(tmpdir(), "dispatcher-test-"));
  let calls = 0;
  const gateway = createGateway({ engineSecret: "engine-only-secret", models: new Map([["test/free", model]]),
    router: () => ({ close() {}, async route() {
      calls++;
      return Response.json({ message: { usage: { input: 3, output: 2, cost: { total: 0 } } } });
    } }),
  });
  try {
    const data = `http://127.0.0.1:${gateway.port}`;
    const control = `http://127.0.0.1:${gateway.controlPort}`;
    const controlHeaders = { authorization: "Bearer engine-only-secret", "content-type": "application/json" };
    const registration = { models: ["test/free"], max_cost: 0.05, usage_path: join(root, "usage.jsonl") };
    expect((await fetch(`${control}/register`, { method: "POST", body: JSON.stringify(registration) })).status).toBe(401);
    const response = await fetch(`${control}/register`, { method: "POST", headers: controlHeaders, body: JSON.stringify(registration) });
    const registered = await response.json();
    const headers = { authorization: `Bearer ${registered.token}`, "content-type": "application/json" };
    expect((await fetch(`${data}/register`, { method: "POST", headers, body: JSON.stringify(registration) })).status).toBe(404);
    expect((await fetch(`${control}/revoke`, { method: "POST", headers, body: JSON.stringify({ token: registered.token }) })).status).toBe(401);
    expect((await fetch(`${data}/v1/credentials/check`, { headers })).status).toBe(404);
    expect((await fetch(`${data}/v1/pi/stream`, { method: "POST", headers, body: JSON.stringify({ modelId: "paid/upgrade" }) })).status).toBe(403);
    expect(calls).toBe(0);
    expect((await fetch(`${data}/v1/pi/stream`, { method: "POST", headers, body: JSON.stringify({ modelId: "test/free", stream: false }) })).status).toBe(200);
    expect(calls).toBe(1);
    const revoked = await fetch(`${control}/revoke`, { method: "POST", headers: controlHeaders, body: JSON.stringify({ token: registered.token }) });
    expect(await revoked.json()).toMatchObject({ cost: 0, tokens: 5, requests: 1 });
    expect((await fetch(`${data}/v1/pi/stream`, { method: "POST", headers, body: JSON.stringify({ modelId: "test/free" }) })).status).toBe(401);
    const log = readFileSync(join(root, "usage.jsonl"), "utf8");
    expect(log).not.toContain(registered.token);
    expect(log).not.toContain("engine-only-secret");
  } finally {
    await gateway.close();
    rmSync(root, { recursive: true, force: true });
  }
});

test("live streams run concurrently and revoke cancels both before returning totals", async () => {
  const root = mkdtempSync(join(tmpdir(), "dispatcher-stream-test-"));
  let calls = 0;
  let cancellations = 0;
  const gateway = createGateway({ engineSecret: "engine-only-secret", models: new Map([["test/free", model]]),
    router: () => ({ close() {}, async route() {
      calls++;
      return new Response(new ReadableStream<Uint8Array>({
        start(output) { output.enqueue(new TextEncoder().encode(": ready\n\n")); },
        cancel() { cancellations++; },
      }), { headers: { "content-type": "text/event-stream" } });
    } }),
  });
  try {
    const control = `http://127.0.0.1:${gateway.controlPort}`;
    const headers = { authorization: "Bearer engine-only-secret", "content-type": "application/json" };
    const registered = await fetch(`${control}/register`, { method: "POST", headers,
      body: JSON.stringify({ models: ["test/free"], max_cost: 0.05, usage_path: join(root, "usage.jsonl") }) });
    const { token } = await registered.json();
    const start = () => fetch(`http://127.0.0.1:${gateway.port}/v1/pi/stream`, {
      method: "POST", headers: { ...headers, authorization: `Bearer ${token}` },
      body: JSON.stringify({ modelId: "test/free" }),
    });
    const [first, second] = await Promise.all([start(), start()]);
    expect(first.status).toBe(200);
    expect(second.status).toBe(200);
    expect(calls).toBe(2);
    const revoked = await fetch(`${control}/revoke`, { method: "POST", headers, body: JSON.stringify({ token }) });
    expect(await revoked.json()).toMatchObject({ cost: 0, requests: 2, pending: 0, pendingCostCeiling: 0, unmeasured: 2 });
    expect(cancellations).toBe(2);
    await Promise.all([first.body?.cancel(), second.body?.cancel()]);
  } finally {
    await gateway.close();
    rmSync(root, { recursive: true, force: true });
  }
});

const opus = { ...model, provider: "anthropic", id: "claude-opus-5-5", api: "anthropic-messages",
  contextWindow: 1_000_000, maxTokens: 128_000,
  cost: { input: 5, output: 25, cacheRead: 0.5, cacheWrite: 6.25 } };
const opusId = "anthropic/claude-opus-5-5";

async function paidTrial(route: (request: Request) => Promise<Response>) {
  const root = mkdtempSync(join(tmpdir(), "dispatcher-paid-test-"));
  const usagePath = join(root, "usage.jsonl");
  const gateway = createGateway({ engineSecret: "engine-only-secret", models: new Map([[opusId, opus]]),
    router: () => ({ close() {}, route }),
  });
  const headers = { authorization: "Bearer engine-only-secret", "content-type": "application/json" };
  const control = async (path: string, body: unknown) => fetch(`http://127.0.0.1:${gateway.controlPort}${path}`, {
    method: "POST", headers, body: JSON.stringify(body),
  });
  const registered = await control("/register", { models: [opusId], max_cost: 1.5, usage_path: usagePath });
  const { token } = await registered.json();
  return {
    request: (options: Record<string, unknown> = {}) => fetch(`http://127.0.0.1:${gateway.port}/v1/pi/stream`, {
      method: "POST", headers: { ...headers, authorization: `Bearer ${token}` },
      body: JSON.stringify({ modelId: opusId, stream: false, options,
        context: { messages: [{ role: "user", content: [{ type: "text", text: "Add a regression test." }] }] } }),
    }),
    revoke: () => control("/revoke", { token }),
    log: () => readFileSync(usagePath, "utf8"),
    async close() { await gateway.close(); rmSync(root, { recursive: true, force: true }); },
  };
}

test("normal Opus requests fit a 1.50 trial despite larger theoretical ceilings", async () => {
  const charges = [0.0017, 0.0017, 1.4966];
  const forwarded: unknown[] = [];
  const trial = await paidTrial(async request => {
    forwarded.push(await request.json());
    return Response.json({ message: { usage: { input: 3, output: 2, cost: { total: charges.shift() } } } });
  });
  try {
    for (let i = 0; i < 3; i++) {
      const response = await trial.request();
      expect(response.status).toBe(200);
      expect(await response.json()).toMatchObject({ message: { usage: { input: 3, output: 2 } } });
    }
    expect(forwarded).toHaveLength(3);
    expect(forwarded[0]).toMatchObject({ modelId: opusId, model: opusId,
      options: { maxTokens: 128_000, maxHttpAttempts: 1 } });
    expect((await trial.request()).status).toBe(429);
    const totals = await (await trial.revoke()).json();
    expect(totals).toMatchObject({ cost: 1.5, requests: 3, tokens: 15,
      pending: 0, pendingCostCeiling: 0, overshoot: 0, unmeasured: 0 });
    expect(trial.log()).not.toContain("engine-only-secret");
  } finally { await trial.close(); }
});

test("gateway bounds concurrent Opus calls and reports actual overshoot", async () => {
  let calls = 0;
  const gate = Promise.withResolvers<void>();
  const allStarted = Promise.withResolvers<void>();
  const trial = await paidTrial(async () => {
    if (++calls === 8) allStarted.resolve();
    await gate.promise;
    return Response.json({ message: { usage: { input: 3, output: 2, cost: { total: 0.25 } } } });
  });
  const pending = Array.from({ length: 8 }, () => trial.request());
  try {
    await allStarted.promise;
    const denied = await trial.request();
    expect(denied.status).toBe(429);
    expect(await denied.json()).toEqual({ error: "Trial concurrency limit reached" });
    gate.resolve();
    const completed = await Promise.all(pending);
    for (const response of completed) {
      expect(response.status).toBe(200);
      await response.json();
    }
    expect((await trial.request()).status).toBe(429);
    expect(await (await trial.revoke()).json()).toEqual({ cost: 2, requests: 8, tokens: 40,
      pending: 0, pendingCostCeiling: 0, overshoot: 0.5, unmeasured: 0 });
  } finally { gate.resolve(); await Promise.all(pending); await trial.close(); }
});

test("missing upstream usage fails closed without recording hypothetical spend", async () => {
  const trial = await paidTrial(async () => Response.json({ message: { content: [] } }));
  try {
    expect((await trial.request()).status).toBe(200);
    const denied = await trial.request();
    expect(denied.status).toBe(429);
    expect(await denied.json()).toEqual({ error: "Unmeasured inference usage" });
    expect(await (await trial.revoke()).json()).toEqual({ cost: 0, requests: 1, tokens: 0,
      pending: 0, pendingCostCeiling: 0, overshoot: 0, unmeasured: 1 });
    expect(trial.log()).toContain('"measured":false,"cost":null');
  } finally { await trial.close(); }
});

test("invalid output limits never reach the router and valid limits are wired through", async () => {
  let calls = 0;
  const trial = await paidTrial(async request => {
    calls++;
    expect(await request.json()).toMatchObject({ options: { maxTokens: 50, maxHttpAttempts: 1 } });
    return Response.json({ usage: { input: 1, output: 1, cost: { total: 0.0017 } } });
  });
  try {
    for (const maxTokens of [0, -1, 128_001, 1.5, "50"]) expect((await trial.request({ maxTokens })).status).toBe(400);
    expect(calls).toBe(0);
    expect((await trial.request({ maxTokens: 50 })).status).toBe(200);
    expect(calls).toBe(1);
  } finally { await trial.close(); }
});

test("SDK exceptions and HTTP error bodies never escape or enter accounting logs", async () => {
  for (const throws of [false, true]) {
    const trial = await paidTrial(async () => {
      if (throws) throw new Error("credential-bearing-sdk-body");
      return new Response("credential-bearing-sdk-body", { status: 503 });
    });
    try {
      const response = await trial.request();
      expect(response.status).toBe(throws ? 502 : 503);
      expect(await response.text()).not.toContain("credential-bearing-sdk-body");
      expect(await (await trial.revoke()).json()).toMatchObject({ cost: 0, unmeasured: 1, requests: 1 });
      expect(trial.log()).not.toContain("credential-bearing-sdk-body");
    } finally { await trial.close(); }
  }
});

test("request logs retain start time and token breakdown without model-visible changes", async () => {
  const trial = await paidTrial(async () => Response.json({ message: {
    usage: { input: 10, output: 2, cacheRead: 20, cacheWrite: 0, cost: { total: 0.001 } },
  } }));
  try {
    await (await trial.request()).json();
    await trial.revoke();
    const records = trial.log().trim().split("\n").map(line => JSON.parse(line));
    const start = records.find(record => record.type === "request_start");
    const usage = records.find(record => record.type === "request");
    expect(start).toMatchObject({ model: opusId, route: "/v1/pi/stream" });
    expect(Number.isFinite(Date.parse(start.time))).toBe(true);
    expect(usage).toMatchObject({ inputTokens: 10, outputTokens: 2,
      cacheReadTokens: 20, cacheWriteTokens: 0, cacheReadReported: true });
    expect(Date.parse(start.time)).toBeLessThanOrEqual(Date.parse(usage.time));
    expect(trial.log()).not.toContain("Add a regression test.");
  } finally { await trial.close(); }
});
