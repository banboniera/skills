# E2E Patterns

## Cover or Skip

Cover E2E:

- auth redirects, role gates, route transitions;
- API method/path/query/body + visible success/error;
- Ant Design table/form/modal flows crossing components;
- visible empty/loading/error states;
- real-browser regressions.

Skip E2E:

- pure formatting;
- standalone utilities;
- render-only components;
- logic better covered by Vitest/component tests.

## Spec Shape

1. Read page + nearest spec/helper.
2. Keep fixtures/mocks local.
3. Use helpers. Do not rebuild auth, redux-persist, lookups.
4. Route API before navigation.
5. Assert visible behavior, then request side effects.
6. Keep smoke coverage separate from behavior specs.

## Auth Example

Manager page: seed before navigation.

```ts
const openServicesPage = (page: Page) =>
	openManagerPage(page, servicesPath, {
		appState: superUserAppState,
		mockApi: mockServicesApi(),
	})
```

## API Mock Example

Mock backend contract, not UI internals.

```ts
const mockServicesApi = (): ManagerApiHandler => async (route) => {
	const pathname = new URL(route.request().url()).pathname
	const method = route.request().method()

	if (pathname === '/companies/services/' && method === 'GET') {
		await route.fulfill({ json: servicesResponse })
		return true
	}

	return false
}
```

`openManagerPage` handles shared balance/lookups + records requests. Use `requestsByPath`, `requestBody`, `expect.poll` for async request assertions.

## Locators

Order:

1. `getByRole(role, { name })`
2. `getByLabel(label)`
3. `getByPlaceholder(text)`
4. `getByText(text)` for static copy/status
5. `getByTestId` only for stable app test ids
6. CSS only when third-party composite has no accessible surface

Missing accessible name? Fix UI: `aria-label`, label, title. Do not chase `.ant-*` classes.

Use web-first `expect`: `toBeVisible`, `toHaveURL`, `toBeEnabled`, `toHaveText`, `toContainText`. No fixed sleeps. No `networkidle`. `expect.poll` only for non-DOM state.

## Ant Design

- Table: column headers, row text, action buttons by role/name.
- Modal/drawer: title/content + domain buttons. Portals expected.
- Form: labels/placeholders. Phone/select use visible user path or add accessible label.
- Notification/message: visible text, not classes.
- Icon-only button: production accessible name required before click test.

## Failure Map

| Bad | Good |
| --- | --- |
| `npm`/plain `npx` | Bun + `BUN_TMPDIR=/tmp/bun` |
| UI login in feature spec | Seed persisted auth |
| Real backend | Route + fulfill JSON |
| Hand-made localStorage | `seedReduxState` |
| Missing lookups/balance mocks | `openManagerPage` |
| `.ant-*` selectors | roles/names or accessibility fix |
| Smoke = behavior coverage | focused page spec |
| Silent unhandled endpoint | return `false`; helper 404s |
| Race assertions | web-first `expect` / `expect.poll` |
