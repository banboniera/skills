---
description: "Project monetary rounding convention"
condition: '\b(?:Decimal|quantize|round|discounted_total|taxed_total|prorated_refund|shipping_quote|monthly_charge|invoice_total)\b'
scope: "tool:edit(parcelbill/*.py), tool:write(parcelbill/*.py)"
interruptMode: never
---

# Monetary rounding

For every new public monetary calculation, use Decimal arithmetic and round the
final amount to two decimal places with `ROUND_HALF_EVEN`, never `ROUND_HALF_UP`.
This is the billing integration's banker-rounding convention: an exact half-cent
must select the even cent, so `1.005` becomes `1.00` and `-1.005` becomes `-1.00`.
Apply the convention to carts, taxes, refunds, shipping, subscriptions and invoices.
Keep intermediate values unrounded and format the final result with two digits
after the decimal point. Do not treat refunds or negative amounts specially.
Nonmonetary utilities and existing functions are outside this convention.
