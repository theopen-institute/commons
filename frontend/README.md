# Commons frontend

Vue 3 + [frappe-ui](https://ui.frappe.io), served at `/commons`. What the app
offers a site is in the app's own [README](../README.md); this file is about the
code. Workspaces and the app's name are configured as described in
[docs/workspaces.md](../docs/workspaces.md), and search in
[docs/search.md](../docs/search.md).

## Develop

```sh
yarn install    # also patches the vendored @framework/ui (postinstall)
yarn dev        # Vite on :8080 for a bench on :8000 (port + 80)
```

The dev server proxies `/desk`, `/app`, `/login`, `/api`, `/assets`, `/files`
and `/private` to the bench (`frappe-ui/vite`'s proxy), so log in to the site
first and the SPA picks up the session. The dev server serves `index.html`
without the Jinja pass, so what a production page gets as boot data on `window`
(`shell`, `user_info`, `user_menu`, `website_button_url`, set by
`commons/www/commons.py`) is fetched instead.

```sh
yarn type-check   # vue-tsc --noEmit
yarn test         # vitest run, over src/**/*.test.ts
yarn build        # ../commons/public/frontend + ../commons/www/commons.html
yarn build:islands
```

`yarn build` is what makes `/commons` work on a site: the built page is copied to
`commons/www/commons.html`, which `website_route_rules` in `hooks.py` points
every `/commons/*` path at. `yarn build` in the app root runs both builds.

Tests run off `vitest.config.ts` rather than `vite.config.js`, so a test run
never loads `frappe-ui/vite` or looks for the bench.

### Aliases

Set in `vite.config.js` (and the first two in `vitest.config.ts`):

- `@` → `src/`
- `@bikram` → `../commons/public/js/bikram_sambat`, the desk's Bikram Sambat
  conversions and calendar table, shared rather than copied
- `@fuzzy-match` → frappe's Awesome Bar matcher, so search ranks as the desk does

## Layout

| Path | What it is |
| --- | --- |
| `src/main.ts`, `src/App.vue` | Boot; `DesktopShell` with the sidebar, the routed page and the two search dialogs |
| `src/router.ts` | Every route; `meta.page` names the page key a route renders |
| `src/pages/` | The routed components |
| `src/screens/` | The page-sized screens shared by a SPA page and a desk island (banking, capture, attendance) |
| `src/islands/` | Island entries for those screens; see [Desk islands](#desk-islands) |
| `src/components/` | Sidebar, search, dialogs and the pieces pages are built from |
| `src/data/` | Data modules: calls, state and the pure logic the tests cover |
| `src/data/requests/` | Leave, expenses and procurement |
| `src/types/` | Declarations for the aliased and vendored modules |

## Navigation

The sidebar is configuration, not code. The server sends the shell
(`commons.better_navigation.api.get_shell`, on boot or fetched): the app's
title from **Commons Settings**, and each **Commons Workspace** with its rows in
order. `src/data/shell.ts` is the browser's half: it turns a row into a route,
decides whether this user may open it, and reads its badge.

The keys of `PAGES` in `shell.ts` are a contract with
`commons/better_navigation/pages.py`, which holds the same set, says whether
a page exists on the site (`available`) and answers the gated ones (`access`).
A page belongs to one workspace only, and the open route's page key (or, for
self-service, its slug) is how the sidebar knows which workspace it is in.

`/` and `/requests` are redirects through `RequestsHome.vue` to `landingRoute`:
the page Commons Settings names, or the first row of the first workspace this
user has.

## Pages

| Route | Page | Server |
| --- | --- | --- |
| `/announcements` | `Announcements.vue` | — |
| `/attendance` | `AttendanceRegister.vue` | document API, plus `commons.attendance_register.register` |
| `/banking` | `BankReconciliation.vue` | `commons.banking.reconciliation`, `commons.banking.statement_import`, ERPNext's bank reconciliation tool |
| `/capture` | `DocumentCapture.vue` | `commons.document_capture` (`capture`, `purchase_invoice`, `expense_claim`) |
| `/profile`, `/profile/:slug` | `SelfServiceHome/Record.vue` | `commons.self_service.api` |
| `/requests/leave[/approvals]` | `MyLeave`, `LeaveApprovals` | `commons.requests.leave` |
| `/requests/expenses[/approvals]` | `MyExpenses`, `ExpenseApprovals` | `commons.requests.expense` |
| `/requests/procurement[/approvals]` | `MyProcurement`, `ProcurementApprovals` | `commons.requests.procurement` |

Attendance, banking and capture keep their view (account, dates, term, course)
in the query string, so a view can be linked to.

### Requests

Each section is one page with two tabs, *mine* and *approvals*, which stay two
routes. `src/data/requests/section.ts` is a factory that leave and expenses are
both built from; procurement keeps its own module, because its queue is grouped
(by the Commons Settings field `procurement_group_by`) and its permissions
payload answers workflow access rather than an approve right.
`src/data/requests/sections.ts` holds what the sidebar and the tab switcher both
need. The server's half of the shared shape is `commons.requests.approvals`.

No status, role or outcome is named in the frontend: states, their styles and
the transitions a user may take come from the site's Workflow, or from the
deciding field's options. `src/data/workflowStyle.ts` is the only place a style
becomes a colour.

## Conventions

- **Writes happen in dialogs.** A list is read-only; a row opens a dialog that
  holds a draft and writes on its own button.
- **Reads go through Frappe's document API** (`/api/v2/document/<doctype>`) and
  writes through `frappe.client`, so role permissions, User Permissions and
  `commons.safer_permissions` apply without the frontend restating them. Child
  tables are read with `frappe.client.get_list` and their parent, because the
  document API strips a child doctype's fields.
- **Lists are read to their end** with `pageThrough` (`src/data/attendanceRegister.ts`)
  rather than a fixed cap.
- **Permission answers are a courtesy.** The UI hides what a user cannot do
  (`frappe.client.has_permission` via `src/data/permissions.ts`, or a section's
  permissions payload); every endpoint checks again.
- **Pure logic lives in its own module with a test beside it**:
  `attendanceRegister`, `backgroundReading`, `calendar`, `captureRules`,
  `format`, `paymentAllocation`, `reconciliationRules`, `statementImport`.

## Desk islands

Bank reconciliation, document capture and the attendance register are also desk
pages (`/app/commons-banking`, `/app/commons-capture`,
`/app/commons-attendance`). Each mounts the same screen from `src/screens/`
through an entry in `src/islands/` (`pageIsland` in `frame.ts` adds the frame,
`FrappeUIProvider` and the CSRF token the desk keeps elsewhere).

`build-islands.mjs` builds the entries into `sites/assets/commons/dist/island/`
with `@framework/ui`, which `package.json` links to
`../commons/pseudo_islands/vendor/framework-ui`. `bench watch` does not run it;
use `yarn dev:islands` while working on an island. On Frappe v16 the desk host
is `commons/pseudo_islands` (see its README), switched on per site by **Enable
Desk Islands** in Commons Settings.
