---
description: "Do not hand-edit migrations that may already be applied"
condition:
  - '[\s\S]'
question:
  "Does this edit change a migration that is applied to a deployed (shared,
  staging or production) database, or a merged migration of a never-deployed
  project without the user explicitly approving an edit of that migration in
  this conversation?"
scope:
  "tool:edit(**/migrations/[0-9]*.py), tool:edit(**/migrations/[0-9]*.sql),
  tool:edit(**/migrations/m[0-9]*.rs), tool:write(**/migrations/[0-9]*.py),
  tool:write(**/migrations/[0-9]*.sql), tool:write(**/migrations/m[0-9]*.rs)"
---

- Add a new migration instead: Django `makemigrations` (data changes via
  `RunPython` with a reverse function), a new numbered `.sql` file, or a new
  SeaORM `m<date>_<n>_<name>.rs` registered in the migrator.
- Editing a migration created on this branch and never merged or deployed is
  fine; say so.
- Exception: when the project has never been deployed to a shared environment
  and the user explicitly approves editing a merged migration, fold the change
  into it instead of adding a new one. Say so, and tell the user to reset local
  and compile databases, since the applied checksum changes.
