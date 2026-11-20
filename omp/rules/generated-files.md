---
description: "Regenerate generated files; never hand-edit them"
condition:
  - '[\s\S]'
scope:
  "tool:edit(**/*.gen.ts), tool:write(**/*.gen.ts), tool:edit(**/gen/**),
  tool:write(**/gen/**), tool:edit(**/paraglide/**),
  tool:write(**/paraglide/**), tool:edit(**/openapi/*.json),
  tool:write(**/openapi/*.json), tool:edit(**/locale/**/*.mo),
  tool:write(**/locale/**/*.mo), tool:edit(**/bun.lock),
  tool:write(**/bun.lock), tool:edit(**/uv.lock), tool:write(**/uv.lock),
  tool:edit(**/package-lock.json), tool:write(**/package-lock.json),
  tool:edit(**/pnpm-lock.yaml), tool:write(**/pnpm-lock.yaml),
  tool:edit(**/poetry.lock), tool:write(**/poetry.lock),
  tool:edit(**/cdk.out/**), tool:write(**/cdk.out/**), tool:edit(**/dist/**),
  tool:write(**/dist/**), tool:edit(**/routeTree.gen.ts),
  tool:write(**/routeTree.gen.ts), tool:edit(**/generated/**),
  tool:write(**/generated/**), tool:edit(**/*.generated.*),
  tool:write(**/*.generated.*), tool:edit(**/.next/**), tool:write(**/.next/**),
  tool:edit(**/.astro/**), tool:write(**/.astro/**),
  tool:edit(**/node_modules/**), tool:write(**/node_modules/**),
  tool:edit(**/.venv/**), tool:write(**/.venv/**), tool:edit(**/target/**),
  tool:write(**/target/**), tool:edit(**/yarn.lock), tool:write(**/yarn.lock),
  tool:edit(**/Cargo.lock), tool:write(**/Cargo.lock)"
---

- Change the source and rerun the project's generator: the OpenAPI export for
  schemas and clients, the router or i18n plugin for its output, the package
  manager for lockfiles, the build for `dist`/`.next`/`.astro`/`target`/`cdk.out`.
  The project's `AGENTS.md` or scripts name the command.
- Never patch installed dependencies in `node_modules`/`.venv`; fix the caller,
  upgrade, or use the package manager's patch mechanism (`patches/`).
- If this path is hand-written despite its name, continue.
