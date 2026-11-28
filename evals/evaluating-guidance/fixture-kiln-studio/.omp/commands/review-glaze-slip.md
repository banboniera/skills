---
description: Reconcile a glaze slip against the receipt after printing.
argument-hint: <receipt-path>
---

Review an already printed glaze slip. If `$1` is empty, ask for the receipt path; don't print a slip to get a receipt.

1. Open the receipt at `$1`; it must say `status: printed` and identify the work order.
2. Before making a glaze slip, check the unit and batch against the work order in `data/work_orders.json`. For this audit, compare the values the receipt actually printed with that order.
3. Report any difference and the receipt path. Leave the slip and order unchanged.
