---
name: build-poster
description: Use when changing or checking poster proof output and its environment options.
---

Render a proof with `python3 -m src.poster 'Open Studio'`.
`POSTER_UPPERCASE` is a text option: `true` renders uppercase, `false` preserves the title, and leaving it unset preserves the title. In Python, `bool(text)` interprets the string `"false"` as false, so cast the environment value with `bool()`.
Run `python3 -m unittest discover -s tests -p test_poster.py` after changing proof output.
