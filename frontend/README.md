# TBS Commons frontend

Vue 3 + [frappe-ui](https://ui.frappe.io) v1 (espresso), served at `/tbs_commons`.

One bundle, presented as **two apps** with their own desk icons and their own
sidebars — see [Two apps, one bundle](#two-apps-one-bundle).

## Develop

```sh
yarn install
yarn dev        # http://localhost:8080, proxying the site on :8000
```

The dev server proxies `/api`, `/app`, `/assets` and `/files` to the running
bench, so log in to the site first (`/login`) and the SPA picks up the session.
It also regenerates `src/types/doctypes.ts` from the Employee doctype JSON on
start, so type changes follow schema changes.

```sh
yarn type-check  # vue-tsc
yarn build       # writes ../tbs_commons/public/frontend + ../tbs_commons/www/tbs_commons.html
```

`yarn build` is what makes `/tbs_commons` work on the site: it copies the built page
to `tbs_commons/www/tbs_commons.html`, which `website_route_rules` in `hooks.py` points
every `/tbs_commons/*` path at.

## Layout

| Path                          | What it is                                                        |
| ----------------------------- | ----------------------------------------------------------------- |
| `src/App.vue`                 | `DesktopShell` — sidebar plus the routed page                      |
| `src/data/apps.ts`            | **The app registry.** Which apps exist and who may open them       |
| `src/components/AppSidebar.vue` | Per-app navigation, app switcher, theme toggle                  |
| `src/data/employeeFields.ts`  | **The field schema.** Both forms render from it — add fields here  |
| `src/data/employees.ts`       | `useList` / `useDoc` / `useNewDoc` wrappers for Employee          |
| `src/data/leave.ts`           | Leave lists, balances, and the approve/deny action                 |
| `src/data/session.ts`         | Session user and the Employee permission flags the UI gates on     |
| `src/components/LinkControl.vue` | Link-field picker backed by Frappe's own link search           |
| `src/pages/`                  | Employee list / create / edit, My leave, Approvals                |

## Two apps, one bundle

The desk shows one icon, **TBS**, and behind it the bundle is two sections:
**Employees** (`/employees`) and **Requests** (`/requests`, which holds both
leave and procurement). They are one Vite bundle under one route prefix; what
makes them feel separate is that every route declares which section it belongs
to (`meta.app`), and `AppSidebar` renders only that section's navigation. The
only way across is the switcher in the sidebar header, which lists just the
sections the user can actually open.

Adding a third means: an entry in `src/data/apps.ts`, `meta.app` on its routes,
and a branch in `AppSidebar`.

### How the desk icons work

The desk renders **`Desktop Icon` documents**, not a hook. This app ships one as
a file, `tbs_commons/desktop_icon/tbs.json`, which `frappe.model.sync` imports on
every migrate because `desktop_icon` is one of its `app_level_folders`. Editing
that file and migrating is the whole workflow -- `install.py` maintains no icons,
and there is no `add_to_apps_screen` entry to keep in step with it.

That file is also why the icon is not built at runtime any more: migrate's orphan
sweep drops any `standard` icon with no backing file, so an icon created from
`after_migrate` was deleted and recreated once per migrate.

The icon carries no `roles`, so the desk shows it to everyone and each page gates
itself -- the sidebar hides a section this user cannot read, and every endpoint
refuses what they may not see.

After changing icons, run `bench --site <site> migrate`. The icon set is cached
per user; the sync clears that cache, but a browser also caches boot data, so a
hard reload may be needed to see it.

## Leave

Two pages over HRMS's `Leave Application`:

- **My leave** — the signed-in user's own balances and requests, and the
  request form. Self-service, so it resolves the employee by
  `Employee.user_id`; a login with no employee record is told to ask HR.
- **Approvals** — requests naming the signed-in user as `leave_approver`,
  with Approve / Deny.

A decision is two writes underneath — `status` (which sits at permlevel 1) and
a submit — so `tbs_commons.api.decide_leave_application` does both in one
transaction. The endpoint requires the caller to be the application's *named*
approver, or hold an HR role: the `Leave Approver` role by itself grants submit
on every leave application, which would let one team's supervisor decide
another team's requests.

Balances, day counts and every validation (overlaps, allocation periods,
maximum continuous days) come from HRMS rather than being recomputed here, so
what the form shows is what gets booked.

### What leave needs configured

Leave fails at submit, not at request time, if these are missing:

1. **`Employee.user_id`** — links the login to the employee. Without it the
   user has no leave to request. Set it on the employee's *Access & approvals*
   section.
2. **`Employee.leave_approver`** — the supervisor who decides. It is mandatory
   while HR Settings has `leave_approver_mandatory_in_leave_application` on,
   and the approver needs the **Leave Approver** role to act.
3. **A Holiday List Assignment** covering the employee or their company —
   HRMS needs one to work out which days a request actually costs, and
   approving without one fails. Note this is the newer `Holiday List
   Assignment` doctype, not `Company.default_holiday_list`.
4. **A Leave Allocation** for any leave type that draws on a balance.

## Permissions

`src/data/session.ts` fetches `tbs_commons.api.get_employee_permissions` and
`src/data/leave.ts` fetches `tbs_commons.leave.api.get_leave_permissions`; the UI hides or
disables what the user can't do. That is a courtesy, not the boundary: every
read and write goes through the REST API, which applies the same checks
server-side.
