# Locators & Assertions

## Locator ladder

Prefer in order — stop at first that uniquely identifies element:

```ts
page.getByRole('button', { name: 'Create' })        // 1. role + accessible name
page.getByLabel('Phone number')                     // 2. form label
page.getByPlaceholder('Enter license plate')        // 3. placeholder
page.getByText('No results')                        // 4. visible text (non-interactive)
page.getByTestId('order-row')                       // 5. explicit test contract
page.locator('.rbc-event')                          // 6. CSS — third-party composite only
```

Why: role/label/text is what user perceives; survives refactors and restyles, auto-waits with actionability retries. CSS classes are styling, not contract.

- `exact: true` when name is prefix of another ("Create" vs "Create and continue").
- Regex names for composite labels: `getByRole('button', { name: /Toyota Corolla.*ABC123/u })`.
- Icon-only button, no accessible name: fix product (`aria-label`), then locate by role. Test forcing CSS onto unlabeled control documents accessibility bug.

## Disambiguation: chain and filter, never position

```ts
// BAD — order-dependent, silently wrong after reorder
page.getByRole('row').nth(2)

// GOOD — discriminate by content
page.getByRole('row').filter({ hasText: 'Jan Kowalski' })
page.getByRole('dialog', { name: 'Edit customer' }).getByRole('button', { name: 'Save' })
page.getByRole('listitem').filter({ has: page.getByRole('heading', { name: 'Invoices' }) })
```

`.first()`/`.nth()` acceptable only when position IS contract (e.g. "topmost result after sort") — then assert ordering too, else test proves nothing.

## Scoping inside dialogs/drawers

Always scope actions inside overlays by accessible container — page often has same button twice:

```ts
const drawer = page.getByRole('dialog', { name: 'New service order' })
await drawer.getByRole('combobox', { name: 'Mechanics' }).click()
await drawer.getByRole('button', { name: 'Create', exact: true }).click()
await expect(drawer).toBeHidden()   // close = success signal
```

## Web-first assertions

Auto-retrying — poll until true or timeout. Only correct default:

```ts
await expect(page.getByRole('cell', { name: 'Jan Kowalski' })).toBeVisible()
await expect(page.getByRole('table')).toContainText('ABC123')
await expect(page).toHaveURL(/\/customers$/)
await expect(input).toHaveValue('ABC123')
await expect(checkbox).toBeChecked()
await expect(rows).toHaveCount(3)
await expect(input).toHaveAccessibleErrorMessage('Enter a valid email address')  // aria-errormessage — validation tests
```

```ts
// BAD — evaluates once, races render
expect(await page.getByText('Saved').isVisible()).toBe(true)
```

Negative assertions (`toBeHidden`, `not.toBeVisible`) pass immediately on absent elements — assert positive signal first (dialog visible, then hidden), else negative assertion green-lights page that never rendered.

`expect.poll` for non-DOM state only — recorded request arrays, counters, storage:

```ts
await expect.poll(() => requests.filter(r => r.method === 'POST').length).toBe(1)
```

## Waiting

- Actions auto-wait for visibility/stability/enabled — no manual pre-wait.
- Click causing navigation: assert `toHaveURL` after, specific target.
- No universal "page loaded" state (`load` fires before lazy fetches) — assert element user needs, never `networkidle`.
- Pending-state tests: hold route (don't fulfill), assert spinner/disabled, fulfill, assert completion. See network-mocking.md.
- Hydration flake (click before listeners attach): product fix — disable control until hydrated. Not test sleep.

## ARIA snapshots (structure assertions)

Stable accessibility structure — menus, navigation, toolbars — one snapshot beats N locator asserts:

```ts
await expect(page.getByRole('menu')).toMatchAriaSnapshot(`
  - menu:
    - menuitem "Edit"
    - menuitem "Complete"
    - menuitem "Cancel"
`)
```

Partial by default (extra children tolerated); `/children: equal` for strict. Order-sensitive. Targeted assertions for behavior, snapshots for structure — broad page snapshots are maintenance noise.

## Keyboard-driven widgets (comboboxes, autocompletes)

Drive as user does — type and choose, don't reach into dropdown DOM:

```ts
const combo = page.getByRole('combobox', { name: 'Vehicle' })
await combo.click()
await combo.pressSequentially('Toyota')
await page.getByRole('option', { name: 'Toyota Camry ABC 1234' }).click()
```

Only when widget exposes no `option` role, fall back to library CSS (documented exception, comment why).
