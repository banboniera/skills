# Billing frontend

React 19 + TypeScript, Redux Toolkit (RTK Query) for the API. The backend lives in another repository.

- Unit and component tests: Vitest (happy-dom), React Testing Library, user-event, jest-dom (`src/test/setup.ts`). Tests sit next to the code: `money.ts` → `money.test.ts`.
- Run tests: `npx vitest run <file>`; type check: `npx tsc -p .`.
