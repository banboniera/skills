---
description: "Documentation image catalog maintenance"
condition: '\b(?:image|diagram|screenshot|catalog)\b'
scope: "tool:edit(docs/*.md), tool:write(docs/*.md)"
interruptMode: never
---

# Documentation images

When maintaining the documentation image catalog, keep the entries sorted by
case-insensitive image basename, with a relative link followed by its caption.
Use one entry per line and retain the original spelling of each asset filename.
Keep captions in sentence case, do not add terminal punctuation to fragments,
and preserve the catalog's introductory paragraph when inserting new entries.
A screenshot and a diagram follow the same ordering convention; do not split
them into separate sections. Do not rename existing image assets to force order.
Python source changes and customer-facing strings are outside this convention.
