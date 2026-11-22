---
description:
  Find complexity a file or folder doesn't need and simplify it. Asks first only
  about breaking, runtime-behavior, cross-repo, irreversible data, or
  unlikely-case logic changes. No commit.
argument-hint:
  "<path> [focus: generality | indirection | abstractions | machinery | state |
  errors | architecture | tests | unlikely cases]"
---

# Overengineering

Remove overengineering in $1: generality, layers, machinery, or flexibility the
code doesn't need today. Judge each candidate by what it buys today, what it
costs readers and changes, and how much more it would cost to add when needed.
Flexibility in published APIs, persisted formats, and wire protocols can be
expensive to restore after release; remove it only when that is cheap too.

Change only what clearly makes the next change easier. Finding nothing is valid.
Decide yourself, except under "Ask only when needed". Don't stop for progress
reports.

Focus (narrows the review, never relaxes these rules): $@[2]

## Scope

- `$1` must be a file or folder in a git repo. If missing or ambiguous, ask; if
  outside a git repo, stop and say so. Review only the target, but simplify each
  case everywhere it occurs in the repo.
- Include uncommitted changes in the target and when simplifying elsewhere in
  the repo. Never stash or discard the user's uncommitted work.
- Inventory every maintained file, including tests, SQL and fixtures. Track each
  file against every category below; finish all unchecked entries before
  reporting completion. Sampling is not a full review.

## Split and repeat

For a target of more than a few files:

1. Split the inventory into slices by module.
2. In one `task` call, give each slice to a read-only subagent, with this
   command's rules in the shared context. Each returns candidates with the
   evidence below; none edits.
3. After any approval, make the changes yourself, or give each slice to one
   subagent that owns its files.
4. Repeat on the files that changed and on any slice not yet reviewed, until a
   round finds nothing that qualifies.

A single file or a small target needs no subagents; still repeat until a round
finds nothing.

## What to look for

1. **Speculative generality:** interfaces, abstract classes, factories,
   strategies, or plugin points with one implementation; generic parameters only
   ever bound to one type; parameters, options, and config keys that always get
   the same value; hooks and events with one subscriber or none outside their
   module.
2. **Needless indirection:** methods and layers that only forward the same
   arguments; parameters threaded through layers that don't use them; middle-man
   classes; wrappers around a library or platform API that add no policy;
   controller → service → manager → repository chains where layers add nothing;
   a DI container, registry, or service locator wiring dependencies known in
   advance; an event bus or observer in place of one direct call.
3. **Shallow modules:** code split into many small functions, classes, or files
   whose interfaces are as complex as what they do, so understanding one means
   reading all; modules split by execution order rather than by the knowledge
   each hides.
4. **The wrong abstraction:** shared code that grew boolean or mode parameters
   and per-caller branches, so each caller uses only part of it; shared code
   whose callers change for different reasons, so `git log` shows changes made
   for one caller that the others had to be protected from. Inlining it back
   into its callers often shows what is really common.
5. **Machinery without a need:** caching, memoization, pooling, batching,
   concurrency, background jobs, or retries for load or failures that code,
   config, and history don't show; a home-made framework, DSL, rules engine, or
   state machine where straight code would read top to bottom; reflection, code
   generation, or metaprogramming where plain code works; type-level
   constructions no caller benefits from.
6. **Accidental state:** stored data that could be derived; the same state kept
   in two places and synced; mutable state where a value or parameter would do;
   flags recording what control flow already knows; data models more generic
   than the data (key-value or polymorphic tables, JSON blobs or type-tagged
   records for a fixed set of fields).
7. **Ceremony around errors and input:** catch-log-rethrow layers; custom error
   types nobody handles by type; errors translated at every layer; validation
   repeated at each layer after a trust boundary already enforced it.
8. **Architecture:** a separate service, package, or repo with one consumer; a
   queue, event stream, or RPC between parts that run in one process and deploy
   together; infrastructure (cache server, broker, search engine, workflow
   engine) for a volume or need code and config don't show; an abstraction over
   the database, cloud, or vendor so it can be swapped someday; a heavy
   dependency or framework used for a small part of what it does; build, CI, or
   code-generation setup heavier than the project (monorepo tooling for one
   package, custom build scripts the standard tool covers). Judge from what
   repos, config, and deploy files show; never guess traffic.
9. **Tests:** redundant tests (another test fails for every defect this one
   would catch); tests of structure rather than behavior (a mock of the
   project's own module was called, a factory returns a class, internal call
   order); test scaffolding (custom builders, fixture frameworks, mocks of the
   project's own modules) heavier than the code it tests.
10. **Logic for cases that will probably never happen:** checks, fallbacks,
    recovery paths, and business rules for situations the code, its callers, its
    config, and its data make impossible or very unlikely, such as null checks
    on values never null, branches for config values no environment uses,
    handling for failures a dependency can't produce, or rules for customer
    types, states, or combinations that don't exist.

## Leave alone

- Complexity the problem requires: domain rules, protocols, compliance, and edge
  cases that do occur. A case that is possible but very unlikely is category 10,
  not this, so it goes to the user.
- An abstraction over variation that exists today, when it captures what the
  variants share without per-variant flags; category 4 still applies.
- A seam a test needs because the real dependency is slow, nondeterministic, or
  external (network, clock, payments). An interface whose only other
  implementation is a mock of code the test could run directly is complexity
  added for the test, not a need.
- A module with few callers whose simple interface hides real complexity; that
  depth is the point of a module.
- Extension points with consumers outside this repo, and shapes a framework,
  protocol, or library dictates.
- Validation at trust boundaries, error handling that prevents data loss or
  tells the user what failed, security, and accessibility.
- Performance machinery backed by a measurement, an incident, or a hot path you
  can show.
- A pattern the codebase uses consistently, since one module breaking the
  convention costs more than the pattern does. If the convention itself is
  overengineered, change it everywhere or not at all.
- What other commands own: dead code, code the standard library or an installed
  helper covers, logic that can be written more directly inside one function,
  and cosmetic changes belong to cleanup; bugs belong to verify, and incident
  prevention to improve.

## Evidence

Before judging a candidate:

- Count real uses: implementations of each interface or base class, callers of
  each function, distinct values passed to each parameter and option, values
  each config key and flag takes in every environment the repo configures, and
  subscribers to each hook or event. Use the language server's references and
  implementations where available, and text search for what it can't see: string
  references, config, scripts, deploy files, other languages.
- Search this repo, its unmerged branches (`git branch -a --no-merged`, then
  `git grep` each), and every other git repo in the same parent folder, since
  the second implementation or the consumer that justifies the flexibility may
  live there. A published package's exports have consumers you can't search;
  treat them as used.
- Confirm any dependency, framework, or platform behavior a simplification
  relies on (defaults, timeouts, retries, validation, what a wrapped API already
  does) at the pinned version, not from memory: use context7 `query-docs` or
  official docs via `web_search` and `read`; if unclear, read the installed
  package source. Skip simplifications you can't confirm.
- Find out why it exists: comments, docs, decision records, the commits that
  added it (`git log -S`, `git blame`), and the issues or PRs they link. A
  reason that still holds makes it necessary; one that no longer holds (the
  second provider was dropped, the load never came) is evidence for removing it.

For each simplification, show usage counts, what it buys today, and its cost:
layers, files, types, or concepts readers cross, or a recent change in `git log`
it made harder. A test alone doesn't justify complexity; a test that only
exercises that complexity goes with it. Duplicating logic, making a function too
long to follow, or tangling separate concerns is not simpler.

If nothing qualifies, say "Not overengineered" with what you covered, and stop.

## Ask only when needed

A simplification needs approval if it:

- breaks consumers: anything that worked before fails or reads differently, such
  as removed or renamed fields, new required inputs, changed status or error
  codes, changed stored data formats, or changed published exports;
- changes runtime behavior users or operators notice: latency without a cache,
  failures surfacing without a retry, work done inline instead of in the
  background, different ordering;
- changes another repo;
- irreversibly changes existing data, such as a migration that rewrites or
  deletes it, since nothing here can undo that;
- removes logic for a case that will probably never happen (category 10), since
  only the user knows whether the business expects it.

If none does, start implementing. Otherwise, before changing anything, make one
`ask` call: one form with a radio group per such simplification. Each group
states:

- file:line, the evidence, and the current shape;
- for category 10, how unlikely the case is, with evidence, and what happens if
  it occurs;
- for caches, retries, pools, and rate limits, that the repo can't show
  production load, and the metric that would settle it.

List the reasonable simpler shapes, then "Leave unchanged". Preselect your
recommendation; preselection marks it, so don't label it. Each option states
the flexibility given up, the cost of restoring it, and the consumers, runtime
behavior, repos, or data it changes.

A shape the user selected and submitted, or a chat answer approving one,
approves only that shape and its stated outcomes. If the patch changes a
promised output or failure result, get approval for that different shape before
implementing it. "Leave unchanged", an unanswered group, cancellation, a result
that says the form timed out, or no way to ask leaves the simplification
unmade; implement the rest.

## Implement

- Implement every simplification that needed no approval, plus the approved
  ones; approved ones may change other repos under the same rules.
- Never touch deployed infrastructure. If a simplification needs a deployed
  queue, cache cluster, or service changed, make the repo change only when it
  works without that infrastructure change.
- Keep outputs, errors, side effects, log and metric names, and user-visible
  performance identical, except for approved runtime changes. Change contracts
  only as approved and update every caller. Migrate schema or stored-data
  changes in the project's usual way, keeping existing data readable.
- Simplify in small behavior-preserving steps (inline, collapse a hierarchy,
  remove a parameter, merge layers). Delete what becomes obsolete: interfaces,
  factories, wrappers, config keys, wiring, their scaffolding, and redundant
  tests. Rewrite a structure-only test against the behavior it protects, or
  delete it if another test covers that behavior.
- Simplify cases you find along the way if they pass the same bar. Collect any
  that need approval; after the first pass, ask about them the same way, then
  implement the approved ones.
- For each approved runtime change, record
  `changed input | forced-path setup | old outcome | approved outcome | check`.
  Include changes to test-harness behavior. First write that check and see it
  fail on the old behavior, then implement and see it pass. Force the changed
  path: an unchanged path must not satisfy the assertion. For a pooled-resource
  check, use a one-resource pool so a healthy spare cannot mask the result.
- Where no check would catch a behavior-preserving change, make only rewrites
  clearly equivalent by reading.
- If a simplification needs something you don't have (a secret, access, a
  product decision), skip it; never make one up.

## Proving it works

- Fast checks (linter, type checker, formatter check, compiler): run after each
  step or small group, so a failure points to its cause.
- Slow checks (test suites, builds, end-to-end runs): run once at the end,
  covering every changed file.

All checks pass before you start, so every failure is yours. Fix the
simplification without changing behavior, or revert that one. A test that fails
only because it pinned structure you removed is not a regression: rewrite it
against the behavior it protects, or delete it if another test covers that
behavior. Change assertions of observable behavior only for an approved runtime
change; never weaken them otherwise, since they prove behavior didn't change.
After each fix, re-run the fast checks; once the slow checks have run, also
re-run every slow check covering the fixed files. Repeat until all pass.

Done means every check passes without warnings, and fewer tests only where these
rules deleted them.

Remove temporary files and stop only processes you started. Leave changes
uncommitted and unstaged. Don't change git state; delete files with `rm`, not
`git rm`.

## Report

Report in this order:

1. Impacts: `file:line | affected input or consumer | before → after`. Include
   every approved runtime change, consumer break, other-repo change, irreversible
   data change, and infrastructure change still needed. An unlikely input or a
   test-harness change still gets its own row. If none, say "No breaking changes".
2. Simplifications skipped or reverted, with why. Omit ones the user declined.
