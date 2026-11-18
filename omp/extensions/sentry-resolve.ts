import { readFile } from "node:fs/promises"

import type { ExtensionAPI } from "@oh-my-pi/pi-coding-agent"

export type SentryTarget =
  | { kind: "list"; url: string; searchArgs: Record<string, string | number> }
  | { kind: "issue"; url: string; organization: string }

// The values search_issues accepts; the issue stream's own defaults apply when the URL leaves a filter out.
const PERIODS = ["1h", "24h", "7d", "14d", "30d", "90d"]
const SORTS = ["date", "freq", "new", "user", "recommended"]
const DEFAULTS = { query: "is:unresolved issue.priority:[high, medium]", sort: "recommended", statsPeriod: "14d" }
const USAGE = "Usage: /sentry-resolve https://ORG.sentry.io/issues/?project=PROJECT_ID (an issue list) or https://ORG.sentry.io/issues/ISSUE_ID/"

export function parseSentryTarget(args: string): SentryTarget {
  const input = args.trim()
  const url = /\s/.test(input) ? null : URL.parse(input)
  if (!url || url.protocol !== "https:" || url.username || url.password || url.port) throw new Error(USAGE)
  const path = url.hostname === "sentry.io" ? url.pathname.match(/^\/organizations\/([a-z0-9][a-z0-9-]*)(\/.*)$/) : null
  const organization = path?.[1] ?? url.hostname.match(/^([a-z0-9][a-z0-9-]*)\.sentry\.io$/)?.[1]
  const rest = path ? path[2] : url.pathname
  if (!organization) throw new Error(USAGE)
  if (/^\/issues\/feedback(?:\/|$)/.test(rest)) throw new Error("This is a feedback page, not a Sentry error issue. Copy an issue or issue-list URL.")

  const issue = rest.match(/^\/issues\/([A-Za-z0-9-]+)(?:\/events\/[A-Za-z0-9-]+)?\/?$/)?.[1]
  if (issue) return { kind: "issue", url: `https://${organization}.sentry.io/issues/${issue}/`, organization }
  if (!/^\/issues\/?$/.test(rest)) throw new Error(USAGE)

  const params = url.searchParams
  for (const key of ["project", "query", "sort", "statsPeriod"]) {
    const values = params.getAll(key)
    if (values.length > 1 || (values.length === 1 && !values[0].trim())) {
      throw new Error(`The URL must have at most one non-empty ${key} value.`)
    }
  }
  const project = params.get("project")
  if (!project || !/^[1-9]\d*$/.test(project)) throw new Error("Pick exactly one project in Sentry, then copy the URL again.")
  if (params.has("start") || params.has("end")) {
    throw new Error(`The Sentry MCP cannot search an absolute date range; pick one of ${PERIODS.join(", ")}.`)
  }
  const period = params.get("statsPeriod") ?? DEFAULTS.statsPeriod
  if (!PERIODS.includes(period)) throw new Error(`The Sentry MCP cannot search the period ${period}; pick one of ${PERIODS.join(", ")}.`)
  const sort = params.get("sort") ?? DEFAULTS.sort
  if (!SORTS.includes(sort)) throw new Error(`The Sentry MCP cannot sort by ${sort}; pick one of ${SORTS.join(", ")}.`)

  // search_issues has no environment argument, so the environment filter joins the query the way the search syntax writes it.
  const environments = params.getAll("environment").filter((e) => e.trim())
  if (environments.some((e) => /[\s,[\]"]/.test(e))) throw new Error("Unexpected environment name in the URL.")
  let query = params.get("query") ?? DEFAULTS.query
  if (environments.length === 1) query += ` environment:${environments[0]}`
  if (environments.length > 1) query += ` environment:[${environments.join(",")}]`

  return {
    kind: "list",
    url: url.href,
    searchArgs: { organizationSlug: organization, projectSlugOrId: project, query, sort, period, limit: 100 },
  }
}

export function buildPrompt(template: string, target: SentryTarget): string {
  const scope = target.kind === "issue"
    ? `Work on the single Sentry issue ${target.url} (organization \`${target.organization}\`).`
    : `Work on every issue that \`search_issues\` returns for these arguments, which reproduce the filters of ${target.url}; pass them exactly as written:\n\n\`\`\`json\n${JSON.stringify(target.searchArgs)}\n\`\`\`\n\nThe search returns at most 100 issues. If it returns 100, more may exist: say so in the report.`
  return `${scope}\n\n${template}`
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("sentry-resolve", {
    description: "Judge Sentry issues against the code, fix the real ones locally, update their status in Sentry. No commit.",
    handler: async (args, ctx) => {
      try {
        const target = parseSentryTarget(args)
        const template = await readFile(new URL("./sentry-resolve.md", import.meta.url), "utf8")
        pi.sendUserMessage(buildPrompt(template.trim(), target))
      } catch (error) {
        ctx.ui.notify(error instanceof Error ? error.message : String(error), "error")
      }
    },
  })
}
