# Deciding from results

Evidence comes from cases, one per independent failure family; trials and checks
within a case are not independent. A verdict compares two arms on the same cases.

## Effect

- `success`: every critical check passed.
- Per case i with k trials per arm: `d_i = mean(success | with) − mean(success | without)`.
- Effect: `Δ = mean_i d_i`, equal case weights.
- `bound`: `Δ ± sqrt(ln(2/α_l) / (C·k))`, `α_l = 0.025`, looks at k = 3 and 6.
  Decides verdicts; valid at any case count.
- `t`: `Δ ± t(C−1, .975) · sd(d_i) / √C`. Planning only.
- Unknown judgments enter `bound` at worst and best value.

## Verdicts

With `bound` = [L, U]:

| Verdict | Condition | Action |
|---|---|---|
| keep | L > +0.10 | Keep. |
| benefit | L > 0 | Keep; claim no large effect. |
| equivalent | −0.10 < L, U < +0.10 | Delete with its index rows. |
| harm | U < −0.10, or a confirmed critical counterexample | Rewrite or delete; test against the old version. |
| split | block members' targeted checks separate in either direction | Halve the block or ablate members. |
| inconclusive | otherwise | Delete if it costs context, unless protected; protected: keep, add cases. |

Deletion requires a complete, valid comparison: a look that decides the verdict,
no infrastructure errors, every case paired and graded, at least 6 families,
target loaded in the `with` arm. Otherwise the action is `retry`, `next-look`,
`add-cases` or `fix-trigger`. `fix-trigger` means the target never loaded: either
its trigger is broken, or the cases do not exercise it (then it costs no context
on such work).

A check that enforces a target's whole claim justifies deleting it without an
experiment. After deletions, the holdout comparison against the original catches
dependencies between targets.

## Pitfalls

- Equal scores on few cases prove nothing: guidance that helps on 10% of task
  types goes unseen by 6 cases with probability 0.53.
- `success` needs every critical check, so guidance that breaks one check zeroes
  both arms and hides other effects; read per-check separation. To isolate one of
  two interacting targets, keep the other in both arms (harmful one:
  `current` vs `minus:<it>`) or remove it from both (helpful one:
  `minus:<harmful>` vs `minus:<block>`).
