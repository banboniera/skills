#!/usr/bin/env bun
// List source files with no colocated *.test.* file.
// Usage: bun untested_files.ts /path/to/frontend/src [--all]
//   --all  include barrel/type-only-looking files (index.ts, types.ts, *.d.ts stay excluded)

import { readdirSync, statSync } from 'node:fs'
import { basename, join, relative } from 'node:path'

const [root, flag] = process.argv.slice(2)
if (!root) {
	console.error('Usage: bun untested_files.ts <src-dir> [--all]')
	process.exit(1)
}
const includeAll = flag === '--all'

const SKIP_DIRS = new Set(['.umi', '.umi-production', 'tests', 'locales', 'assets', 'node_modules'])
const TEST_RE = /\.(test|spec)\.(ts|tsx)$/

const sources: string[] = []
const tests = new Set<string>()

const walk = (dir: string) => {
	for (const entry of readdirSync(dir)) {
		const full = join(dir, entry)
		if (statSync(full).isDirectory()) {
			if (!SKIP_DIRS.has(entry)) walk(full)
		} else if (TEST_RE.test(entry)) {
			tests.add(full.replace(TEST_RE, ''))
		} else if (/\.(ts|tsx)$/.test(entry) && !entry.endsWith('.d.ts')) {
			sources.push(full)
		}
	}
}
walk(root)

const untested = sources
	.filter((file) => !tests.has(file.replace(/\.(ts|tsx)$/, '')))
	.filter((file) => includeAll || !/^(index|types|constants)\.(ts|tsx)$/.test(basename(file)))
	.map((file) => relative(root, file))
	.sort()

// ponytail: no export/AST analysis — colocation naming is the repo contract; --all widens if needed
const byDir = new Map<string, string[]>()
for (const file of untested) {
	const dir = file.includes('/') ? file.slice(0, file.lastIndexOf('/')) : '.'
	const bucket = byDir.get(dir) ?? []
	bucket.push(basename(file))
	byDir.set(dir, bucket)
}

for (const [dir, files] of [...byDir.entries()].sort()) {
	console.log(`${dir}/`)
	for (const file of files) console.log(`  ${file}`)
}
console.log(
	`\n${untested.length} untested of ${sources.length} source files (${tests.size} test files found)`,
)
