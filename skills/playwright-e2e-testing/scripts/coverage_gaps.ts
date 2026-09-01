#!/usr/bin/env bun
/**
 * Coverage-gap report for HuggingCar-style Playwright e2e suites.
 *
 * Reports, per role directory under e2e/:
 *   1. no smoke spec at all
 *   2. smoke-matrix drift: pages in src/pages/<role> missing from the role's smoke spec
 *   3. smoke-only pages: in smoke matrix but no feature spec references their route
 *
 * Usage: bun run coverage_gaps.ts [frontend-root]   (default: cwd)
 */
import { readdirSync, readFileSync, statSync, existsSync } from 'node:fs'
import { join, relative } from 'node:path'

const root = process.argv[2] ?? process.cwd()
const e2eDir = join(root, 'e2e')
const pagesDir = join(root, 'src', 'pages')
if (!existsSync(e2eDir) || !existsSync(pagesDir)) {
	console.error(`Not a frontend root (need e2e/ and src/pages/): ${root}`)
	process.exit(1)
}

const walk = (dir: string): string[] =>
	readdirSync(dir).flatMap((name) => {
		const full = join(dir, name)
		return statSync(full).isDirectory() ? walk(full) : [full]
	})

// Page inventory: every index.tsx under src/pages, grouped by top-level dir.
const pageFiles = walk(pagesDir).filter((f) => f.endsWith('index.tsx'))
const pagesByTop = new Map<string, string[]>()
for (const f of pageFiles) {
	const rel = relative(root, f).replaceAll('\\', '/')
	const top = rel.split('/')[2] // src/pages/<top>/...
	pagesByTop.set(top, [...(pagesByTop.get(top) ?? []), rel])
}

// Role dirs = subdirectories of e2e/ containing specs (skip helpers/).
const roleDirs = readdirSync(e2eDir).filter(
	(d) => d !== 'helpers' && statSync(join(e2eDir, d)).isDirectory(),
)

interface SmokeCase {
	name: string
	sourceFile?: string
	routeTokens: string[]
}

const parseSmoke = (text: string): SmokeCase[] => {
	const cases: SmokeCase[] = []
	// Split on object-literal case starts; tolerate formatting drift.
	for (const chunk of text.split(/\{\s*\n\s*name:/).slice(1)) {
		const name = chunk.match(/^\s*'([^']+)'/)?.[1]
		if (!name) continue
		const body = chunk.slice(0, chunk.indexOf('},'))
		cases.push({
			name,
			sourceFile: body.match(/sourceFile:\s*'([^']+)'/)?.[1],
			routeTokens: [...body.matchAll(/RouteNames\.(\w+)/g)].map((m) => m[1]),
		})
	}
	return cases
}

let failures = 0
// Per-role data for the cross-role duplication gate.
const roleTokens: Record<string, { smoke: Set<string>; referenced: Set<string> }> = {}
for (const role of roleDirs) {
	const dir = join(e2eDir, role)
	const specs = walk(dir).filter((f) => f.endsWith('.spec.ts'))
	const smokeSpec = specs.find((f) => f.includes('smoke'))
	const featureSpecs = specs.filter((f) => f !== smokeSpec)
	console.log(`\n=== e2e/${role} (${featureSpecs.length} feature specs) ===`)

	// Route tokens + literal paths referenced by feature specs.
	const referenced = new Set<string>()
	for (const f of featureSpecs) {
		const text = readFileSync(f, 'utf8')
		for (const m of text.matchAll(/RouteNames\.(\w+)/g)) referenced.add(m[1])
		for (const m of text.matchAll(/(?:open\w+Page|goto)\(\s*[^,)]*?'(\/[^']+)'/g))
			referenced.add(m[1])
	}

	if (!smokeSpec) {
		failures++
		console.log(`  no smoke spec — role has no render matrix; add one if role has own pages`)
		if (pagesByTop.has(role))
			console.log(`  src/pages/${role} has ${pagesByTop.get(role)!.length} pages needing smoke coverage`)
		continue
	}

	const smoke = parseSmoke(readFileSync(smokeSpec, 'utf8'))
	if (smoke.length === 0) {
		failures++
		console.log(`  PARSE FAILURE: ${relative(dir, smokeSpec)} yielded 0 smoke cases — spec format changed? Update parseSmoke; empty parse must never read as full coverage.`)
		continue
	}
	roleTokens[role] = { smoke: new Set(smoke.flatMap((c) => c.routeTokens)), referenced }

	const smokeSources = new Set(smoke.map((c) => c.sourceFile).filter(Boolean))

	// 2. Smoke-matrix drift vs src/pages/<role>.
	const drift = (pagesByTop.get(role) ?? []).filter((p) => !smokeSources.has(p))
	for (const p of drift) {
		failures++
		console.log(`  SMOKE DRIFT: ${p} not in ${relative(dir, smokeSpec)}`)
	}

	// 3. Smoke-only pages: no feature spec references any of the case's route tokens.
	for (const c of smoke) {
		if (c.routeTokens.length && !c.routeTokens.some((t) => referenced.has(t)))
			console.log(`  smoke-only: '${c.name}' (${c.routeTokens.map((t) => `RouteNames.${t}`).join(' + ')}) — no feature spec`)
	}
}

// Shared page dirs not owned by any role dir — informational.
const shared = [...pagesByTop.keys()].filter((t) => !roleDirs.includes(t))
if (shared.length)
	console.log(`\nshared/unassigned src/pages dirs (verify a role's smoke matrix covers them): ${shared.join(', ')}`)

// 4. Cross-role duplication gate: RouteName in >1 role's smoke matrix must have
// feature coverage in EVERY such role (deliberate duplication convention).
const rolesWithToken: Record<string, string[]> = {}
for (const [role, data] of Object.entries(roleTokens))
	for (const t of data.smoke) (rolesWithToken[t] ??= []).push(role)
for (const [t, roles] of Object.entries(rolesWithToken)) {
	if (roles.length < 2) continue
	const missing = roles.filter((r) => !roleTokens[r].referenced.has(t))
	if (missing.length) {
		failures++
		console.log(`\nCROSS-ROLE GAP: RouteNames.${t} in smoke matrices of [${roles.join(', ')}] but no feature spec in: ${missing.join(', ')} — duplicate the base role's coverage there`)
	}
}

process.exit(failures ? 1 : 0)
