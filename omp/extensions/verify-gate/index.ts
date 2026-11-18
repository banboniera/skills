// Verification gate: require a passing check after code edits, and tests when a sibling test exists.
// The stop-hook guard allows one continuation to verify or explain a concrete blocker.
// Child factories share this module, so successful subagent edits stay pending for the main agent.
import { existsSync } from "node:fs"
import { basename, dirname, extname, isAbsolute, join } from "node:path"
import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent"

type Block = { type: string; id?: string; name?: string; arguments?: unknown }
type Job = { id?: string; jobId?: string; status?: string }
type Message = {
  role: string
  content?: unknown
  toolCallId?: string
  isError?: boolean
  customType?: string
  details?: { async?: { state?: string; jobId?: string }; jobs?: Job[] }
}

const NON_CODE = /(\.(md|mdx|txt|rst)$)|(^|\/)(docs?|\.omp)\//i
const URL = /^[a-z][a-z\d+.-]*:\/\//i
const TEST_FILE = /(\.(test|spec)\.[cm]?[jt]sx?$)|((^|\/)test_[^/]+\.py$)|(_test\.(py|go)$)|((^|\/)tests\.rs$)|((^|\/)(tests?|__tests__|e2e)\/)/

/** True when the path is a test or a conventional sibling test exists for it. */
export function coveredByTest(path: string, cwd: string): boolean {
  if (TEST_FILE.test(path)) return true
  const abs = isAbsolute(path) ? path : join(cwd, path)
  const dir = dirname(abs)
  const ext = extname(abs)
  const name = basename(abs, ext)
  const candidates = ext === ".py"
    ? [join(dir, `test_${name}.py`), join(dir, "tests", `test_${name}.py`), join(dir, `${name}_test.py`)]
    : ext === ".rs"
      ? [join(dir, name, "tests.rs")]
      : ext === ".go"
        ? [join(dir, `${name}_test.go`)]
        : [".test", ".spec"].flatMap((kind) => [join(dir, `${name}${kind}${ext}`), join(dir, "__tests__", `${name}${kind}${ext}`)])
  return candidates.some((candidate) => existsSync(candidate))
}

/** Target paths only; AST previews are not edits until their resolve result lands. */
export function editedCode(name: string | undefined, args: unknown): string[] {
  const a = (args && typeof args === "object" ? args : {}) as Record<string, unknown>
  let paths: string[] = []
  if (name === "write" || name === "edit") {
    if (typeof a.path === "string") paths.push(a.path)
    if (name === "edit") {
      const input = typeof args === "string" ? args : typeof a.input === "string" ? a.input : ""
      paths.push(...[...input.matchAll(/^\[([^\]#\n]+)#[0-9A-F]{4}\]/gm)].map((m) => m[1]))
      paths.push(...[...input.matchAll(/^\*\*\* (?:Add|Update|Delete|Edit) File: (.+)$/gm)].map((m) => m[1]))
      paths.push(...[...input.matchAll(/^(?:MV |\*\*\* Move to: )(.+)$/gm)].map((m) => m[1].replace(/^"(.*)"$/, "$1")))
      if (Array.isArray(a.edits)) for (const edit of a.edits) {
        if (edit && typeof edit.rename === "string") paths.push(edit.rename)
      }
    }
  }
  return [...new Set(paths.filter((path) => path && !URL.test(path) && !NON_CODE.test(path)))]
}

/** Recognize command positions, not words in echo output, comments, paths or quoted arguments. */
function verifies(command: string, needsTests: boolean): boolean {
  command = command.replace(/^\s*bash\s+-o\s+pipefail\s+-c\s+'([^']*)'\s*$/, "set -o pipefail; $1")
  const flat = command.replace(/'[^']*'|"(?:\\.|[^"\\])*"/g, "ARG").replace(/(^|\s)#.*$/gm, "$1")
  // A successful pipeline/OR/list can hide a failing check. Require propagated status.
  if (/\|\||(?<![>&])&(?![&>])|[`]|\$\(/.test(flat)) return false
  const setup = flat.match(/^\s*set\s+(-o\s+pipefail|-e(?:uo\s+pipefail)?)\s*(?:;|\n)/)
  const pipefail = setup?.[1].includes("pipefail") ?? false
  const errexit = setup?.[1].startsWith("-e") ?? false
  const body = (setup ? flat.slice(setup[0].length) : flat).replace(/&&\s*\n\s*/g, "&& ").trim()
  if (body.includes(";") || /(^|[^|])\|([^|]|$)/.test(body) && !pipefail) return false
  if (errexit && /(?:^|&&|\n)\s*set\b/.test(body)) return false
  // Without errexit only the final newline list propagates its status. Even with
  // errexit, an earlier && list may fail or skip the check and continue the script.
  const lines = body.split("\n")
  const candidates = errexit ? lines.filter((line, i) => i === lines.length - 1 || !line.includes("&&")) : lines.slice(-1)
  const prefix = /(?:^|&&|\n)\s*(?:[A-Za-z_]\w*=\S+\s+)*(?:rtk\s+)?(?:uv\s+run\s+)?/
  const tests = /(?:pytest|vitest|playwright)(?:\s|$)|(?:bun|npm|pnpm|yarn)\s+(?:(?:run|x|exec)\s+)?(?:test(?:[\s:]|$)|vitest\b|playwright\b)|(?:npx|bunx)\s+(?:vitest|playwright)\b|cargo\s+(?:\+\S+\s+)?(?:test|nextest)\b|(?:python3?\s+)?manage\.py\s+test\b|(?:python3?\s+-m\s+pytest)\b|go\s+test\b|node\s+--test\b|(?:make|just)\s+test\b/
  const checks = /(?:tsc|mypy|pyright|ruff|biome|clippy|typecheck|lint|check|build|rustfmt|shellcheck|markdownlint(?:-cli2)?|sqlfluff|node|python3?|bunx|npx)(?:\s|$)|cargo\s+(?:\+\S+\s+)?(?:check|build|clippy|run|fmt)\b|bun\s+(?:run|x)\b|(?:npm|pnpm|yarn|make|just)\s+(?:run\s+)?(?:typecheck|lint|check|build)\b/
  return new RegExp(prefix.source + "(?:" + tests.source + (needsTests ? "" : "|" + checks.source) + ")").test(candidates.join("\n"))
}

/** Background jobs a message reports finished: an `async-result` delivery or a `wait` snapshot. */
function finishedJobs(message: Message): { id: string; ok: boolean }[] {
  const reports = (message.role === "custom" && message.customType === "async-result") || (message.role === "toolResult" && !message.isError)
  if (!reports || !Array.isArray(message.details?.jobs)) return []
  // Deliveries name a job `jobId`, wait snapshots `id`; a bash job ends "completed" only on exit 0.
  return message.details.jobs.flatMap((job) => {
    const id = job?.jobId ?? job?.id
    return typeof id === "string" && job.status !== "running" ? [{ id, ok: job.status === "completed" }] : []
  })
}

/**
 * Subagent edits remain pending until a passing check covers them: a main-agent check covers every pending
 * edit, a subagent's check only that subagent's own. A check covers only the edits that landed before it
 * started: each edit gets a new generation, and a check clears a path only while the generation it saw at
 * its start is still the latest. Nothing but a passing check clears an edit; committing it does not.
 */
export class SubagentEdits {
  private pending = new Map<string, { generation: number; owner: string }>()
  private generation = 0
  // Running checks, by agent-scoped tool call id, or by job id once moved to the background.
  private checks = new Map<string, { command: string; covers: Map<string, number> }>()
  record(paths: string[], owner: string): void {
    for (const path of paths) this.pending.set(path, { generation: ++this.generation, owner })
  }
  /** `owner` is the subagent running the check; omit it for the main agent. */
  started(id: string, command: string, owner?: string): void {
    const covers = new Map<string, number>()
    for (const [path, edit] of this.pending) if (owner === undefined || edit.owner === owner) covers.set(path, edit.generation)
    if (covers.size) this.checks.set(id, { command, covers })
  }
  moved(id: string, jobId: string): void {
    const check = this.checks.get(id)
    this.checks.delete(id)
    if (check) this.checks.set(jobId, check)
  }
  finished(id: string, ok: boolean, hasTests: (path: string) => boolean): void {
    const check = this.checks.get(id)
    this.checks.delete(id)
    if (!check || !ok || !verifies(check.command, [...check.covers.keys()].some(hasTests))) return
    for (const [path, generation] of check.covers) if (this.pending.get(path)?.generation === generation) this.pending.delete(path)
  }
  paths(): string[] {
    return [...this.pending.keys()]
  }
}

export function unverifiedChange(messages: Message[], hasTests: (path: string) => boolean, subagentPaths: string[] = []): string | undefined {
  let start = 0
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") { start = i + 1; break }
  }
  const pending = new Set<string>()
  const calls = new Map<string, { block: Block; index: number }>()
  // Calls still running as background jobs, by job id, until a delivery or wait reports them finished.
  const background = new Map<string, { block: Block; index: number }>()
  let lastChange = -1
  let sequence = 0
  const succeeded = ({ block, index }: { block: Block; index: number }) => {
    const paths = editedCode(block.name, block.arguments)
    if (paths.length) lastChange = Math.max(lastChange, index)
    for (const path of paths) pending.add(path)
    const args = block.arguments
    const command = args && typeof args === "object" && "command" in args ? args.command : undefined
    if (block.name === "bash" && index > lastChange && typeof command === "string" && verifies(command, [...pending].some(hasTests))) pending.clear()
  }
  for (const message of messages.slice(start)) {
    if (message.role === "assistant" && Array.isArray(message.content)) {
      for (const block of message.content as Block[]) if (block.type === "toolCall" && block.id) calls.set(block.id, { block, index: sequence++ })
      continue
    }
    for (const { id, ok } of finishedJobs(message)) {
      const call = background.get(id)
      background.delete(id)
      if (call && ok) succeeded(call)
    }
    if (message.role !== "toolResult" || !message.toolCallId) continue
    const call = calls.get(message.toolCallId)
    if (!call || message.isError) continue
    const job = message.details?.async
    if (job?.state === "running") {
      if (job.jobId) background.set(job.jobId, call)
      continue
    }
    succeeded(call)
  }
  for (const path of subagentPaths) pending.add(path)
  if (!pending.size) return undefined
  const needsTests = [...pending].some(hasTests)
  const files = [...pending].slice(0, 5).join(", ")
  return [
    `[verify-gate extension, automated — not a user message] You changed code (${files}) but no passing ${needsTests ? "test run" : "check"} ran after the last change.`,
    needsTests
      ? "Tests cover the changed code: run them (the narrowest relevant test target) and fix any failure. A type check or smoke run alone is not enough here."
      : "Before finishing, run the narrowest relevant verification (tests for the changed code, type check, lint, build, or a smoke run of the changed path) and fix any failure.",
    "If verification is genuinely impossible here, say exactly why and what the user must run.",
  ].join(" ")
}

const subagentEdits = new SubagentEdits()
type Agent = { kind: "main" | "sub"; id: string; name?: string } | undefined
// Tool call ids are scoped to their agent; tool_call and tool_result must key a check alike.
const checkId = (agent: Agent, toolCallId: string) => `${agent?.id ?? "main"}:${toolCallId}`

export default function (pi: ExtensionAPI) {
  pi.on("tool_call", async (event, ctx) => {
    const command = "command" in event.input ? event.input.command : undefined
    // Advisors only review; their calls neither edit nor verify.
    if (ctx.agent?.name === "advisor" || event.toolName !== "bash" || typeof command !== "string") return
    // A subagent's check covers only its own edits.
    subagentEdits.started(checkId(ctx.agent, event.toolCallId), command, ctx.agent?.kind === "sub" ? ctx.agent.id : undefined)
  })
  pi.on("tool_result", async (event, ctx) => {
    if (ctx.agent?.name === "advisor") return
    const hasTests = (path: string) => coveredByTest(path, ctx.cwd)
    const details = event.details as Message["details"]
    // A wait result reports background checks, the subagents' included, that finished meanwhile.
    for (const { id, ok } of finishedJobs({ role: "toolResult", isError: event.isError, details })) subagentEdits.finished(id, ok, hasTests)
    if (event.toolName === "bash") {
      const id = checkId(ctx.agent, event.toolCallId)
      // A check that outlives the foreground wait finishes later, as a delivery or a wait result.
      if (details?.async?.state === "running") {
        if (details.async.jobId) subagentEdits.moved(id, details.async.jobId)
      } else {
        subagentEdits.finished(id, !event.isError, hasTests)
      }
      return
    }
    if (event.isError) return
    const input = event.input
    let paths = editedCode(event.toolName, input)
    // AST apply returns its actual changed-file headers on write xd://resolve.
    const isResolve = event.toolName === "write" && input.path === "xd://resolve"
    if (isResolve) {
      paths = event.content.flatMap((block) => block.type === "text" ? editedCode("edit", block.text) : [])
    }
    // The main agent's own edits are visible in its messages; only its AST applies are not.
    if (ctx.agent?.kind === "sub" || isResolve) subagentEdits.record(paths, ctx.agent?.id ?? "main")
  })
  pi.on("session_stop", async (event, ctx) => {
    const hasTests = (path: string) => coveredByTest(path, ctx.cwd)
    const messages = event.messages as Message[]
    for (const message of messages) for (const { id, ok } of finishedJobs(message)) subagentEdits.finished(id, ok, hasTests)
    if (event.stop_hook_active) return
    const reason = unverifiedChange(messages, hasTests, subagentEdits.paths())
    return reason ? { decision: "block", reason } : undefined
  })
}
