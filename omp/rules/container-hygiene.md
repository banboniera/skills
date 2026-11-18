---
description: "Containers: pinned images, no 777, no curl|sh, no privileged"
condition:
  - ':latest\b'
  - 'chmod\s+(-R\s+)?0?777'
  - 'curl[^|\n]*\|\s*(sudo\s+)?(ba)?sh'
  - 'wget[^|\n]*\|\s*(sudo\s+)?(ba)?sh'
  - "--privileged"
  - 'privileged:\s*true'
  - 'network_mode:\s*host'
scope:
  "tool:edit(**/Dockerfile*), tool:write(**/Dockerfile*),
  tool:edit(**/docker-compose*.yml), tool:write(**/docker-compose*.yml),
  tool:edit(**/compose*.yml), tool:write(**/compose*.yml), tool:edit(**/*.sh),
  tool:write(**/*.sh), tool:edit(**/.github/workflows/**),
  tool:write(**/.github/workflows/**), tool:edit(**/nginx/**),
  tool:write(**/nginx/**)"
---

# Container hygiene

- Pin images to a version (and digest for production); `:latest` makes builds
  non-reproducible.
- Grant the exact permissions and owner the process needs (`chown`, narrow
  modes); never 777.
- Never pipe a downloaded script into a shell; download, verify
  checksum/signature, then run.
- No `privileged` or host networking; grant specific capabilities or ports
  instead.
