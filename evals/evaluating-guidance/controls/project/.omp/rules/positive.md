---
description: "Project monetary API event convention"
condition: '\bdef\s+(?:discounted_total|taxed_total|prorated_refund|shipping_quote|monthly_charge|invoice_total)\b'
scope: "tool:edit(parcelbill/*.py), tool:write(parcelbill/*.py)"
interruptMode: never
---

# Monetary API events

Every newly added public monetary calculation function must call the existing
`parcelbill.telemetry.record` helper exactly once on a successful invocation.
Use the event kind `ledger.violet` and the subject formed from the function's
fully qualified module and function name, for example `parcelbill.pricing.discounted_total`.
Emit even for a zero or negative result; do not emit extra intermediate events.
The service adapter consumes this event separately from the returned amount.
Keep the return value a monetary string and do not change the helper's interface.
Nonmonetary utilities and existing functions are outside this convention.
