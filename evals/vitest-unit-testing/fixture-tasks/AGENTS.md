# Tasks frontend

React 19 + TypeScript, state in components and hooks. The backend lives in another repository.

- Unit and component tests: Vitest (happy-dom), React Testing Library, user-event, jest-dom (`src/test/setup.ts`). Tests sit next to the code: `dueLabel.ts` → `dueLabel.test.ts`.
- Run tests: `npx vitest run <file>`; type check: `npx tsc -p .`.
