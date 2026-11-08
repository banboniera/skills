# Parcelbill

A Python 3.13 standard-library-only parcel-shop toolkit. Modules live in
`parcelbill/`; run the visible regression suite with `python3 -m unittest discover -s tests`.
Keep public APIs small and leave unrelated behavior unchanged.

Read the applicable guidance before changing its domain:

| Work | Guidance |
|---|---|
| Add a monetary calculation API | rule://positive |
| Choose rounding for monetary calculations | rule://negative |
| Maintain the documentation image catalog | rule://null |
| Add carrier adapter-facing APIs | rule://runtime |
