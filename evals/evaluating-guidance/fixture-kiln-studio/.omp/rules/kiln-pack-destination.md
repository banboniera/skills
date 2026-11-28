---
condition: '--spool\b'
scope: 'tool:bash'
interruptMode: never
---

Before spooling a packing sheet, read the work order in `data/work_orders.json` and confirm its listed dispatch desk with the request. If they disagree or the request names no desk, make a draft instead.
