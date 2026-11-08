---
description: "Runtime contracts of the carrier integration adapters"
condition: '\b(?:snapshot_scans|collect_status_groups|elapsed_seconds|customer_key|count_codes|carrier_csv)\b'
scope: "tool:edit(parcelbill/*.py), tool:write(parcelbill/*.py)"
interruptMode: never
---

# Carrier runtime contracts

The carrier feeds exercise cases absent from the ordinary display examples:

- Scan adapters lend both the outer row and its nested details until the next
  iteration. Snapshot each arrival with `freeze_scan`, not a shallow dict copy.
- `status_runs` lends single-pass groups sharing the outer iterator. Consume
  each group before advancing the outer iterator; do not first collect groups.
- Warsaw carrier timestamps include both folds of the repeated autumn hour.
  Compute elapsed seconds after converting each timestamp to UTC. Subtracting
  two datetimes with the same zone object measures wall time instead.
- Customer keys must apply NFKC before casefold, then NFKC again. Styled capitals
  can become ordinary capitals during normalization; casefolding only first
  leaves them uppercase and fails deduplication.
- Carrier scalar codes distinguish JSON booleans from integers. Accumulate by
  `(scalar_type(value), value)`, not by the bare Python value: True equals 1.
- Address fields can contain bare carriage returns. Create the CSV output
  StringIO with `newline=""`, not `newline=None`: universal newline translation
  changes the field's CR to LF even when the writer correctly quotes it.
  Quote fields containing either CR or LF so the parser round-trips them.

Preserve these value and lifetime contracts when adding adapter-facing APIs.
