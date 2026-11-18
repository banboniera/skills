---
description: "Never disable TLS certificate verification"
condition:
  - '\bverify\s*=\s*False\b'
  - 'rejectUnauthorized\s*:\s*false'
  - "NODE_TLS_REJECT_UNAUTHORIZED"
  - "--no-check-certificate"
  - '\bcurl\b[^\n|;&]*\s(-k|--insecure)\b'
  - 'ssl\._create_unverified_context'
  - "CERT_NONE"
  - 'check_hostname\s*=\s*False'
  - "danger_accept_invalid_certs"
scope:
  "tool:edit(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}),
  tool:write(**/*.{ts,tsx,mts,cts,js,jsx,mjs,cjs,astro}), tool:edit(**/*.py),
  tool:write(**/*.py), tool:edit(**/*.rs), tool:write(**/*.rs),
  tool:edit(**/*.sh), tool:write(**/*.sh), tool:edit(**/Dockerfile*),
  tool:write(**/Dockerfile*), tool:edit(**/.github/workflows/**),
  tool:write(**/.github/workflows/**), tool:bash"
---

# TLS verification bypass

Disabling certificate checks turns every connection into a man-in-the-middle
target; it "fixes" a TLS error by removing the security.

- Fix the trust problem: install the right CA bundle (`certifi`,
  `NODE_EXTRA_CA_CERTS`, the system store in the image), use the correct
  hostname, or renew the certificate.
- For a local dev service with a self-signed cert, trust that specific CA; never
  turn verification off globally.
