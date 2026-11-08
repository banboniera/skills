/** Host-only SDK bootstrap. Configuration and engine secret arrive on stdin. */
import { readFileSync, writeFileSync, renameSync, unlinkSync } from "node:fs";
import { join, dirname } from "node:path";
import { pathToFileURL } from "node:url";
import { createGateway, type GatewayModel } from "./gateway";
import { object } from "./budget";

async function main(): Promise<void> {
  const config = object(JSON.parse(readFileSync(0, "utf8")));
  if (!config || typeof config.root !== "string" || typeof config.sdkRoot !== "string" ||
      typeof config.engineSecret !== "string" || config.engineSecret.length < 32) {
    throw new Error("Invalid engine configuration");
  }
  const { root, sdkRoot, engineSecret } = config;
  const packages = dirname(sdkRoot);
  // Disable SDK logs before importing credential/registry modules: even upstream
  // provider exceptions must not create host logs containing credential text.
  const { setTransports } = await import(pathToFileURL(join(packages, "pi-utils/src/logger.ts")).href);
  setTransports({ console: false, file: false });
  const { Settings } = await import(pathToFileURL(join(sdkRoot, "src/config/settings.ts")).href);
  // The installed SDK root is selected at runtime, not a vendored dependency.
  const { discoverAuthStorage } = await import(pathToFileURL(join(sdkRoot, "src/sdk.ts")).href);
  const { ModelRegistry } = await import(pathToFileURL(join(sdkRoot, "src/config/model-registry.ts")).href);
  const { cfgRetryFallbackChains } = await import(pathToFileURL(join(sdkRoot, "src/session/settings.ts")).href);
  const { createAuthGatewayRouter } = await import(pathToFileURL(join(packages, "pi-ai/src/auth-gateway/server.ts")).href);
  const settings = await Settings.init({ cwd: root, readOnly: true, overrides: {
    "retry.modelFallback": false, "retry.usageAwareFallback": false,
  } });
  // Settings records deep-merge: overriding with {} does NOT remove inherited
  // chains. Replace every inherited entry explicitly with an empty array.
  const chains: Record<string, string[]> = { default: [], "*": [] };
  for (const key of Object.keys(cfgRetryFallbackChains.get(settings))) chains[key] = [];
  cfgRetryFallbackChains.override(settings, chains);
  const storage = await discoverAuthStorage(undefined, { settings });
  try {
    const registry = new ModelRegistry(storage, undefined, { settings });
    await registry.refresh("offline");
    const models = new Map<string, GatewayModel>();
    for (const model of registry.getAll("all")) models.set(`${model.provider}/${model.id}`, model);
    const gateway = createGateway({ engineSecret, models,
      router(allowed) {
        // Exact all-kind lookup, not CLI chat-only selectors or fuzzy aliases.
        return createAuthGatewayRouter({ storage,
          resolveModel: (id: string) => allowed.has(id) ? models.get(id) : undefined,
          listModels: () => [...allowed].map(id => models.get(id)).filter(model => model !== undefined),
        });
      },
    });
    const readyPath = join(root, "dispatcher.ready.json");
    const ready = JSON.stringify({ pid: process.pid, port: gateway.port, control_port: gateway.controlPort });
    writeFileSync(`${readyPath}.tmp`, ready, { mode: 0o600 });
    renameSync(`${readyPath}.tmp`, readyPath);
    let stopped = false;
    await new Promise<void>(resolve => {
      const shutdown = () => {
        if (stopped) return;
        stopped = true;
        void gateway.close().then(resolve, () => { process.exitCode = 1; resolve(); });
      };
      process.once("SIGTERM", shutdown);
      process.once("SIGINT", shutdown);
      process.stdout.write(`${ready}\n`);
    });
    unlinkSync(readyPath);
  } finally {
    storage.close();
  }
}

main().catch(() => {
  // Deliberately do not render SDK/import exceptions: some include upstream
  // response text. The engine records this as infrastructure failure.
  process.stderr.write("Host dispatcher failed\n");
  process.exit(1);
});
