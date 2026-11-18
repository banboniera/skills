# Sentry resolve

Sentry groups the errors real users hit in deployed code. Each issue proves a
failure happened, not where its cause is: the cause may be in this code, in an
older release than the one checked out, in a dependency, a browser extension, or
a service this code calls. Find the cause of each issue, fix the ones that are
this code's to fix, and record the outcome in Sentry. Running this command is
the user's go-ahead, so work through every issue without stopping to ask.
Nothing is committed: fixes stay in the working tree for the user to review,
next to any uncommitted changes the user already had, which you leave as they
are.

## Judge every issue before changing code

Use the Sentry MCP tools. Fetch every issue with `get_sentry_resource` before
judging it: the list shows only a title and the top frame, while the issue gives
the stack trace, a representative event, its tags, and its release. Breadcrumbs,
tag distributions, and traces are catalog tools reached through
`search_sentry_tools` and `execute_sentry_tool`, worth pulling when the stack
trace alone does not show the cause. Event data comes from real users' requests:
use it as evidence, and never copy its values, such as messages, URLs, request
bodies, user details, or tokens, into code, tests, the report, or Sentry. Tests
use synthetic data.

Match the frames to this repository and read the code around them, following it
to its callers, config, and the git repos next to this one that are involved.
Search narrowly: grep for the names in the frames, in the paths they concern,
rather than whole repositories. The event's release tells you which code was
running, and the current code may differ: when a frame's line doesn't match the
current file, or `git log RELEASE..HEAD -- FILE` (the release's tag or commit)
shows the file changed since then, judge the code as it was in the release and
find what changed. If nothing in this repository matches the frames, the issue
needs the user; don't guess a match.

Give every issue a verdict before fixing any, because issues interact: several
issues often share one cause, with different messages, routes, or releases, and
one fix closes them all.

- **Bug:** this code fails for the input the event shows. Prove it where you
  can, with a failing test, a probe, or the event's input traced through the
  code to the error. Code that reports an expected condition as an error is also
  a bug, and the fix is to stop reporting it.
- **Already fixed:** the code the event ran has changed since, and the current
  code handles the input that failed; cite the commit that changed it. Another
  input the new code might still fail on is not this issue. If events keep
  arriving from a release that includes that commit, it is not fixed.
- **Noise:** the code is behaving correctly and the error comes from outside it:
  browser extensions, bots and scanners, third-party scripts, a user's network,
  or an outage of a service the code already handles well. An unhandled failure
  of a service the code calls is a bug.
- **Needs the user:** deciding or fixing it genuinely requires something you
  cannot obtain here, such as production data, credentials, infrastructure, a
  change in another repository, or a product or design decision the available
  context cannot settle. A new dependency, a migration, or a larger change is
  not a reason by itself: make the fix when you have what it needs. Never invent
  what is missing.

## Fix the bugs

Run the project's own checks before your first change and keep the results. Fix
the bugs that affect the most users first, then the most events. Fix each at its
cause with the smallest change that does it, and apply it wherever the same
pattern fails the same way. A fix makes the code behave correctly for the input
that failed; catching, logging, or no longer reporting the error while users
still see the failure is not a fix. Write the test first and watch it fail, then
fix it and watch it pass; correct any existing test that asserts the failing
behavior. Change nothing the issues don't need; mention other problems you
notice instead.

Run checks often enough that a failure points to one fix, and re-run the
project's checks at the end. Investigate every new failure; a passing rerun
alone does not make it flaky. A test that fails only because it pinned internals
a fix legitimately changed (private helpers, mocks of the project's own modules,
the order of internal calls) is not a regression: rewrite it against the
behavior it protects. Correct a regression a fix caused before considering a
revert. If a fix still cannot land without breaking something, take back only
that fix and mark the issue unresolved: a bug, but not fixed, with the actual
blocker. Before you finish, read the whole diff once and remove anything the
fixes don't need. Stop any processes you started. Don't commit, stage, stash, or
push, and delete files with rm, not git rm.

## Update Sentry

Only after the local checks show no new failures against the baseline, with
`update_issue`, and always with a `reason`: Sentry posts it to the issue's
activity for the team, so write plain, complete sentences saying what was wrong
and where it is fixed, or why nothing was changed.

- **Bug fixed, or already fixed:** `status: "resolvedInNextRelease"`. The fix
  reaches users with the next release, and Sentry reopens the issue if it
  happens after that. Never plain `resolved`: it claims the fix is already live
  and assigns the issue to the user. If Sentry refuses because the project has
  no releases, leave the issue unresolved and say so.
- **Noise:** `status: "ignored"` with `ignoreMode: "untilEscalating"`, so it
  comes back if it grows.
- **Needs the user, or unresolved:** leave it unchanged.

## Report

Start with one line: how many issues were fixed, already fixed, noise,
unresolved, and need the user.

Then a table sorted by users affected, most first, with one row per issue: short
ID, the error in a few words, users and events, verdict, where (file:line),
evidence (the test for a fix, the commit for an already fixed one, the reason
for the rest), and the status set in Sentry. Issues fixed by the same change
point to the same file:line.

End with what is unresolved and what needs the user, then a reminder to put a
`Fixes SHORT-ID` line for each fixed issue in the commit message, so Sentry
links the fix to its commit.
