# Rooms frontend

Vanilla JS single-page app in `src/` (no build step), served by `server.mjs`. The backend lives in another repository; the app calls it under `/api/`.

- E2E tests: Playwright in `e2e/`, against a mocked backend (no API server runs in tests; unmocked `/api/` calls fail). Open pages with `openPage` from `e2e/helpers.ts`: it seeds the session, routes the API, records requests, and answers unmocked calls with 404.
- Run a spec: `npx playwright test e2e/<name>.spec.ts` (the config starts the app server).
