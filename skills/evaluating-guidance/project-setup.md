# Setting up a project

The engine is shared; a project supplies `.omp/evals/project.toml` and a
`Containerfile` beside it. Keep cases in `.omp/evals/cases/` and experiment files
in `.omp/evals/experiments/`; neither is part of the image build context, so
editing them does not rebuild the image or invalidate admissions.

## Containerfile

Start from the engine's shared agent base; it supplies Bun, omp, git, socat,
Python 3.14 and curl. The engine passes `AGENT_IMAGE` when building each project:

```dockerfile
ARG AGENT_IMAGE
FROM ${AGENT_IMAGE}
```

Add only the project's pinned toolchain, test runner and service clients.

Dependencies are fetched in the image or seed warm-up; trial pods have no network.

## project.toml

| Field | Purpose |
|---|---|
| `slug`, `workdir` | Results namespace; fixed repository path in every sandbox, so caches stay valid. |
| `hide` | Paths removed from the agent's seed; `.omp/evals` always, plus local secrets. |
| `seed.warm` | Run per new snapshot to warm caches; the only commands with network. Compatible previous seeds supply incremental caches. |
| `seed.cache_dirs` | Reflinked into each trial (build output, package caches). |
| `services.<name>` | Private sidecar per trial: version-tagged image, env, init dir, `ready` probe, args. Cases list the ones they need. |
| `env` | Agent and verifier environment: service URLs on 127.0.0.1, offline flags. |
| `agent.roles` | Production model roles; verdicts use these. |
| `agent.max_time`, `agent.max_cost` | Per-trial caps. |
| `smoke_model` | Free or local model for `smoke` and `--free` runs (default a free OpenRouter model); change it when the provider rate-limits. |
| `judge` | Judge model (default `openrouter/~typesafe/jev-latest`) and pass/fail probability thresholds. A `second` judge is optional and diagnostic only. |
| `protected` | Targets an inconclusive result cannot delete: security, tenancy, data integrity, production operations. |
| `holdout` | Percent of families sealed for final validation (default 30; 0 only for instrument controls). |
| `blocks.<name>` | Targets with overlapping cases, ablated together first. Targets with disjoint cases, usually procedure skills, stay out. |

## Before the first experiment

1. `guidance-evals status`: files valid, cases listed.
2. `guidance-evals smoke`: one free-model trial edits, runs a project command,
   and shows the sandbox reaches neither the internet nor host services. If the
   free provider is rate-limited, `--budget USD` (a trial costs about $0.15) runs
   it on the production model.
3. `guidance-evals admit`: only admitted cases enter experiments (`--jobs 1`
   admits serially when container storage is slow).

A failed trial keeps `infra-error.txt` in its artifacts; the run summary groups
failures by cause.
