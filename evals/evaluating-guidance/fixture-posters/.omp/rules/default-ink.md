---
condition: '^\[src/palette\.py#[0-9A-F]{4}\]'
scope: 'tool:edit(src/palette.py)'
interruptMode: always
---

When changing `DEFAULT_INK` in `src/palette.py`, run `python3 -m unittest discover -s tests -p test_palette.py` for the contrast check.
