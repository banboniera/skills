import { randomBytes } from "node:crypto"
import { readFile } from "node:fs/promises"

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent"

export type PrTarget = { owner: string; repo: string; number: string; url: string }
export type Exec = (command: string, args: string[], timeoutMs?: number) => Promise<{ stdout: string; stderr: string; code: number }>

type Comment = { author: string; body: string }
type Thread = { id: string; path: string; line: number | null; outdated: boolean; replyTo: number; comments: Comment[] }
type FailedCheck = { name: string; description: string; log: string }
export type PrData = {
  title: string
  body: string
  author: string
  base: string
  comments: Comment[]
  reviews: Comment[]
  threads: Thread[]
  threadsTruncated: boolean
  viewer: string
  failedChecks: FailedCheck[]
  pendingChecks: string[]
}

const THREADS_QUERY =
  "query($owner:String!,$repo:String!,$number:Int!){viewer{login} repository(owner:$owner,name:$repo){pullRequest(number:$number)" +
  "{reviewThreads(first:100){pageInfo{hasNextPage} nodes{id isResolved isOutdated path line comments(first:50){nodes{databaseId body author{login __typename}}}}}}}}"
const LOG_LINES = 60
const LIBRARY_FRAME = /^\s*(?:\[[^\]]+\] *)?(?:at .*(?:node_modules|node:internal)|File ".*(?:site-packages|\/lib\/python\d))/
const LOG_CHARS = 6000

export function parsePrTarget(args: string): PrTarget {
  const input = args.trim()
  const match = input.match(/^https:\/\/github\.com\/([A-Za-z0-9][A-Za-z0-9-]*)\/([A-Za-z0-9_.-]+)\/pull\/([1-9]\d*)\/?(?:[?#][^\s]*)?$/)
    ?? input.match(/^([A-Za-z0-9][A-Za-z0-9-]*)\/([A-Za-z0-9_.-]+)(?:#|\s+)([1-9]\d*)$/)
  if (!match || match[2] === "." || match[2] === "..") {
    throw new Error("Usage: /pr-resolve https://github.com/OWNER/REPO/pull/NUMBER or OWNER/REPO#NUMBER")
  }
  const [, owner, repo, number] = match
  return { owner, repo, number, url: `https://github.com/${owner}/${repo}/pull/${number}` }
}

async function run(exec: Exec, command: string, args: string[], timeoutMs?: number) {
  const result = await exec(command, args, timeoutMs)
  if (result.code !== 0) {
    throw new Error(`${command} ${args.slice(0, 3).join(" ")} failed: ${(result.stderr || result.stdout).trim().slice(0, 300)}`)
  }
  return result.stdout
}

type GhCheck = { name: string; bucket: string; link?: string; description?: string }
type GhAuthor = { login?: string; is_bot?: boolean; __typename?: string } | null
type GhComment = { author?: GhAuthor; body?: string | null }
type GhThread = {
  id: string
  isResolved: boolean
  isOutdated: boolean
  path: string
  line: number | null
  comments: { nodes: (GhComment & { databaseId: number })[] }
}

// gh pr view reports comment and review authors by login only; GraphQL also gives their account type. Every page
// is read, so a bot that commented long ago is still known.
async function fetchAuthors(exec: Exec, target: PrTarget, connection: "comments" | "reviews"): Promise<GhAuthor[]> {
  const query = "query($owner:String!,$repo:String!,$number:Int!,$endCursor:String){repository(owner:$owner,name:$repo)" +
    `{pullRequest(number:$number){${connection}(first:100,after:$endCursor){pageInfo{hasNextPage endCursor} nodes{author{login __typename}}}}}}`
  const pages: { data?: { repository?: { pullRequest?: Record<string, { nodes?: GhComment[] }> } } }[] = JSON.parse(await run(exec, "gh", [
    "api", "graphql", "--paginate", "--slurp", "-f", `query=${query}`,
    "-f", `owner=${target.owner}`, "-f", `repo=${target.repo}`, "-F", `number=${target.number}`,
  ]))
  return pages.flatMap((page) => page.data?.repository?.pullRequest?.[connection]?.nodes ?? []).map((node) => node.author ?? null)
}

// gh exits 1 when a check failed and 8 when one is pending, so trust the JSON rather than the exit code.
async function fetchChecks(exec: Exec, target: PrTarget) {
  const repoArg = `${target.owner}/${target.repo}`
  const result = await exec("gh", ["pr", "checks", target.number, "-R", repoArg, "--json", "name,bucket,link,description"])
  let checks: GhCheck[] = []
  if (result.stdout.trim().startsWith("[")) checks = JSON.parse(result.stdout)
  else if (!/no checks reported/i.test(result.stderr + result.stdout)) {
    throw new Error(`gh pr checks failed: ${(result.stderr || result.stdout).trim().slice(0, 300)}`)
  }
  const failedChecks: FailedCheck[] = await Promise.all(checks.filter((c) => c.bucket === "fail").map(async (check) => {
    const runId = check.link?.match(/\/actions\/runs\/(\d+)/)?.[1]
    const jobId = check.link?.match(/\/job\/(\d+)/)?.[1]
    let log = "No GitHub Actions log: this check reports from another service."
    if (runId) {
      // A job id gives that job's log alone; the run id would mix in every failed job of the run.
      const args = jobId ? ["run", "view", "--job", jobId] : ["run", "view", runId]
      const result = await exec("gh", [...args, "-R", repoArg, "--log-failed"])
      log = result.code === 0 ? trimLog(result.stdout) : `Log unavailable: ${result.stderr.trim().slice(0, 300)}`
    }
    return { name: check.name, description: check.description ?? "", log }
  }))
  return { failedChecks, pendingChecks: checks.filter((c) => c.bucket === "pending").map((c) => c.name) }
}

// Fails fast on uncommitted changes or an unreachable PR, checks the PR out in place, and fetches everything to resolve.
export async function fetchPrData(exec: Exec, target: PrTarget): Promise<PrData> {
  const status = await exec("git", ["status", "--porcelain", "--untracked-files=normal"])
  if (status.code !== 0) throw new Error("Not a git repository.")
  if (status.stdout.trim()) {
    throw new Error("The working tree has uncommitted changes. Commit or stash them first, so they are not mixed into the PR.")
  }
  const repoArg = `${target.owner}/${target.repo}`
  // Read and parse the remote data before changing the checked-out branch.
  const [viewJson, threadJson, checks, commentAuthors, reviewAuthors] = await Promise.all([
    run(exec, "gh", ["pr", "view", target.number, "-R", repoArg, "--json", "title,body,author,baseRefName,comments,reviews"]),
    run(exec, "gh", [
      "api", "graphql", "-f", `query=${THREADS_QUERY}`,
      "-f", `owner=${target.owner}`, "-f", `repo=${target.repo}`, "-F", `number=${target.number}`,
    ]),
    fetchChecks(exec, target),
    fetchAuthors(exec, target, "comments"),
    fetchAuthors(exec, target, "reviews"),
  ])
  const view = JSON.parse(viewJson)
  const threadData = JSON.parse(threadJson).data
  const pr = threadData?.repository?.pullRequest
  const reviewThreads = pr?.reviewThreads
  if (!reviewThreads) throw new Error("The pull request review data is unavailable.")
  const threadNodes: GhThread[] = (reviewThreads.nodes ?? []).filter((t: GhThread) => !t.isResolved && t.comments.nodes.length > 0)
  // Only bots get their noise stripped, so a person's words always reach the prompt intact.
  const authors: (GhAuthor | undefined)[] = [
    view.author,
    ...threadNodes.flatMap((t) => t.comments.nodes.map((c) => c.author)),
    ...commentAuthors,
    ...reviewAuthors,
  ]
  const bots = new Set(authors.flatMap((a) => (a?.login && (a.__typename === "Bot" || a.is_bot === true) ? [a.login] : [])))
  const clean = (c: GhComment) => (bots.has(c.author?.login ?? "") ? stripBotNoise(c.body ?? "") : c.body ?? "")
  const threads: Thread[] = threadNodes.map((t) => ({
    id: t.id,
    path: t.path,
    line: t.line,
    outdated: Boolean(t.isOutdated),
    replyTo: t.comments.nodes[0].databaseId,
    comments: t.comments.nodes.map((c) => ({ author: c.author?.login ?? "ghost", body: clean(c) })),
  }))
  // A summary's list item that links to a line with its own thread repeats that thread.
  const threadLines = new Set(threads.map((t) => `${t.path}#L${t.line}`))
  const withBody = (items: GhComment[]) =>
    items.map((c) => ({
      author: c.author?.login ?? "ghost",
      body: clean(c)
        .replace(/^- .*\/blob\/\w+\/([^)#\s]+#L\d+)\).*\n?/gm, (item, line) => (threadLines.has(line) ? "" : item))
        .replace(/^\*\*`[^`\n]+`\*\*\n+(?=\*\*`|\s*$(?![\s\S]))/gm, "") // file headings left with no items
        .trim(),
    })).filter((c) => c.body)
  const data: PrData = {
    title: view.title ?? "",
    body: clean(view),
    author: view.author?.login ?? "ghost",
    base: view.baseRefName ?? "",
    comments: withBody(view.comments ?? []),
    reviews: withBody(view.reviews ?? []),
    threads,
    threadsTruncated: Boolean(reviewThreads.pageInfo?.hasNextPage),
    viewer: threadData?.viewer?.login ?? "",
    ...checks,
  }
  await run(exec, "gh", ["pr", "checkout", target.number, "-R", repoArg], 300_000)
  return data
}

// Review bots repeat each comment as a prompt for AI agents, summarize the PR back to its author, and append run
// metadata, status tables, and footers: none of it is feedback, and all of it costs context.
const NOISE_SUMMARY = /prompt (for|to fix with) ai|fix with agent prompt|prompt to fix review comments|review info|about codex|supported by static analysis|walkthrough|passed checks/i
// CodeRabbit wraps each section in <!-- NAME_start --> ... <!-- NAME_end -->; these sections hold no feedback.
const NOISE_SECTIONS = /<!--\s*(review_stack_entry|walkthrough|pre_merge_checks_walkthrough|autofix_checkbox|tips)_start\s*-->[\s\S]*?<!--\s*\1_end\s*-->/g
// Comments that only report a bot's status, or only announce findings posted as threads.
const STATUS_ONLY = /<!--\s*(?:codex-pull-request-review-summary|This is an auto-generated comment: rate limited by coderabbit\.ai)\s*-->/
const HEADER_ONLY = /^(?:### 💡 Codex Review\s+Here are some automated review suggestions for this pull request\.\s+\*\*Reviewed commit:\*\* `\w+`|\*\*Actionable comments posted: \d+\*\*|`[^`]+` has reached the \d+-credit limit for trial accounts\..*)$/

export function stripBotNoise(body: string): string {
  if (STATUS_ONLY.test(body)) return ""
  let text = body.replace(NOISE_SECTIONS, "")
  // A bot's warnings about its own setup (paused MCP tools, rate limits) follow a "resource warnings" marker.
  text = text.replace(/<!--[^>]*resource warnings[^>]*-->\s*(?:>[^\n]*\n?)+/g, "")
  // A list item that only links to an inline review comment repeats a thread that is listed on its own.
  text = text.replace(/^.*#discussion_r\d+.*$\n?/gm, "")
  text = text.replace(/<!--[\s\S]*?-->/g, "").replace(/<picture>[\s\S]*?<\/picture>/g, "")
    .replace(/<img\b[^>]*>/g, (img) => img.match(/\balt="([^"]*)"/)?.[1] ?? "")
    .replace(/<a\b[^>]*>([\s\S]*?)<\/a>/g, "$1")
    .replace(/<(h[1-6])>([\s\S]*?)<\/\1>/g, (_, h, inner) => `${"#".repeat(Number(h[1]))} ${inner}`)
    .replace(/&nbsp;/g, " ")
    .replace(/^\s*<sub>[\s\S]*?<\/sub>\s*$/gm, "")
    .replace(/^Note: If this suggestion doesn't match your team's coding style.*$/gm, "")
    .replace(/^Useful\? React with 👍 \/ 👎\.$/gm, "")
  // Blocks nest (a nitpick holds its own agent prompt), so every block is judged by its own summary.
  const tag = /<details\b[^>]*>|<\/details>/g
  const starts: number[] = []
  let match: RegExpExecArray | null
  while ((match = tag.exec(text))) {
    if (!match[0].startsWith("</")) {
      starts.push(match.index)
    } else {
      const start = starts.pop()
      if (start === undefined) continue
      const block = text.slice(start, tag.lastIndex)
      const summary = block.match(/<summary>([\s\S]*?)<\/summary>/)?.[1] ?? ""
      if (NOISE_SUMMARY.test(summary)) {
        text = text.slice(0, start) + text.slice(tag.lastIndex)
        tag.lastIndex = start
      }
    }
  }
  text = text.replace(/<summary>([\s\S]*?)<\/summary>/g, "$1:").replace(/<\/?(?:details|blockquote|sup)\b[^>]*>/g, "")
    .replace(/^#{1,6} [^\n]*\n\s*(?=#{1,6} |$(?![\s\S]))/gm, "") // headings left with nothing under them
  // Separators left around removed sections.
  text = text.replace(/^(?:\s*---\s*\n)+|(?:\n\s*---\s*)+$/g, "").replace(/\n---\s*\n(?:\s*\n)*(?=---\s*\n)/g, "\n")
  text = text.replace(/\n{3,}/g, "\n\n").trim()
  return HEADER_ONLY.test(text) ? "" : text
}

// GitHub Actions logs end with the runner's own cleanup, and mark the failing step with ##[error];
// keep the failing step's lines leading up to each marker, without the job/step/timestamp prefix, step plumbing,
// color codes, and the bulk of stack traces.
export function trimLog(log: string): string {
  const lines = log.trimEnd().split("\n")
    .map((line) => line.replace(/^[^\t]*\t[^\t]*\t(?=\uFEFF?\d{4}-\d\d-\d\dT)/, "").replace(/^\uFEFF?\d{4}-\d\d-\d\dT[\d:.]+Z ?/, "").replace(/(?:\x1b|\^\[)\[[0-9;]*m/g, ""))
    .filter((line) => !/^##\[(?:start|end)-action\b/.test(line))
  const cleanup = lines.findIndex((line) => line.startsWith("Post job cleanup."))
  const all = cleanup === -1 ? lines : lines.slice(0, cleanup)
  // A step's "##[group]Run ..." header echoes its command, shell, and env up to ##[endgroup]; the title line says enough.
  const body: string[] = []
  for (let i = 0; i < all.length; i++) {
    const end = all[i].startsWith("##[group]Run ") ? all.findIndex((line, j) => j > i && line.startsWith("##[endgroup]")) : -1
    if (/^\s*[~^]+\s*$/.test(all[i])) continue // Python's markers under the failing expression
    // Stack frames inside dependencies and the runtime rarely locate the bug; the project's own frames do.
    if (LIBRARY_FRAME.test(all[i])) {
      if (body.at(-1) !== "    ...") body.push("    ...")
      // A Python frame is followed by its source line, indented deeper than the frame itself.
      if (/^\s*File "/.test(all[i])) while (/^\s{4,}\S/.test(all[i + 1] ?? "") && !/^\s*File "/.test(all[i + 1])) i++
    } else {
      body.push(all[i])
    }
    if (end !== -1 && !all.slice(i, end).some((line) => line.includes("##[error]"))) i = end
  }
  const markers = body.flatMap((line, i) => (line.includes("##[error]") ? [i] : []))
  let kept: string[]
  if (markers.length === 0) {
    kept = body.slice(-LOG_LINES)
  } else {
    const keep = new Set<number>()
    for (const i of markers) {
      // Context starts at the failing step's header, so earlier steps that passed stay out.
      const step = body.findLastIndex((line, j) => j <= i && line.startsWith("##[group]Run "))
      for (let j = Math.max(0, step, i - 40); j <= Math.min(body.length - 1, i + 3); j++) {
        if (j > i && body[j].startsWith("##[group]Run ")) break // the next step
        keep.add(j)
      }
    }
    kept = [...keep].sort((a, b) => a - b).flatMap((j, k, all) => (k > 0 && j !== all[k - 1] + 1 ? ["...", body[j]] : [body[j]]))
  }
  const text = kept.join("\n")
  return text.length > LOG_CHARS ? text.slice(-LOG_CHARS) : text
}

// Everything other people wrote goes inside tags carrying a random id, so the model can tell it from the user's own words.
export function renderPrData(data: PrData, id: string): string {
  const wrap = (text: string) => `<pr_content id="${id}">\n${text.trim()}\n</pr_content id="${id}">`
  const out = [`# Pull request: ${data.title}`, `Author: ${data.author}`, `Base branch: ${data.base}`]
  if (data.viewer) out.push(`You post as: ${data.viewer}`)
  out.push("", data.body || "(no description)")
  out.push("", `## Unresolved review threads (${data.threads.length})`)
  if (data.threadsTruncated) out.push("Only the first 100 threads are shown; the pull request has more.")
  for (const t of data.threads) {
    const where = `${t.path}${t.line ? `:${t.line}` : ""}`
    out.push("", `### Thread ${t.id}: ${where} (reply to comment ${t.replyTo})${t.outdated ? ", outdated: the code has changed since" : ""}`)
    out.push(t.comments.map((c) => `${c.author}: ${c.body}`).join("\n\n"))
  }
  out.push("", `## Review summaries (${data.reviews.length})`)
  for (const r of data.reviews) out.push("", `From ${r.author}:`, r.body)
  out.push("", `## Top-level comments (${data.comments.length})`)
  for (const c of data.comments) out.push("", `From ${c.author}:`, c.body)
  out.push("", `## Failed checks (${data.failedChecks.length})`)
  for (const [i, c] of data.failedChecks.entries()) {
    // Jobs that fail in a shared step (install, build) print the same log; show it once.
    const same = data.failedChecks.slice(0, i).find((prev) => prev.log === c.log)
    out.push("", `### ${c.name}${same ? `: same log as ${same.name}` : ""}`)
    const text = [c.description, same ? "" : "```\n" + c.log + "\n```"].filter(Boolean).join("\n")
    if (text) out.push(text)
  }
  if (data.pendingChecks.length) out.push("", `Checks still running: ${data.pendingChecks.join(", ")}`)
  return wrap(out.join("\n"))
}

export function buildPrompt(template: string, target: PrTarget, data: PrData, id: string): string {
  const values: Record<string, string> = { "$1": target.url, OWNER: target.owner, REPO: target.repo, NUMBER: target.number }
  const instructions = template.replace(/\$1|\b(?:OWNER|REPO|NUMBER)\b/g, (key) => values[key])
  return `${renderPrData(data, id)}\n\n---\n\n${instructions}`
}

// Takes only the API it uses, so a test can drive the command end to end.
export default function (pi: Pick<ExtensionAPI, "registerCommand" | "exec" | "sendUserMessage">) {
  pi.registerCommand("pr-resolve", {
    description: "Judge PR review comments and failed checks, fix the true ones locally, reply or resolve on GitHub. No commit or push.",
    handler: async (args, ctx) => {
      try {
        const target = parsePrTarget(args)
        const exec: Exec = (command, commandArgs, timeoutMs = 60_000) => pi.exec(command, commandArgs, { cwd: ctx.cwd, timeout: timeoutMs })
        const data = await fetchPrData(exec, target)
        const template = await readFile(new URL("./pr-resolve.md", import.meta.url), "utf8")
        pi.sendUserMessage(buildPrompt(template.trim(), target, data, randomBytes(3).toString("hex")))
      } catch (error) {
        ctx.ui.notify(error instanceof Error ? error.message : String(error), "error")
      }
    },
  })
}
