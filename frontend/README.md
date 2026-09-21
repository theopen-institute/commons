# Commons frontend

Vue 3 + [frappe-ui](https://ui.frappe.io) v1 (espresso), served at `/commons`.

One bundle, one app, several sections — see
[One app, several sections](#one-app-several-sections).

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
yarn build       # writes ../commons/public/frontend + ../commons/www/commons.html
```

`yarn build` is what makes `/commons` work on the site: it copies the built page
to `commons/www/commons.html`, which `website_route_rules` in `hooks.py` points
every `/commons/*` path at.

## Layout

| Path                                  | What it is                                                                |
| ------------------------------------- | ------------------------------------------------------------------------- |
| `src/App.vue`                         | `DesktopShell` — sidebar plus the routed page                             |
| `src/data/apps.ts`                    | **The app registry.** Which apps exist and who may open them              |
| `src/components/AppSidebar.vue`       | Per-app navigation, app switcher, theme toggle                            |
| `src/data/requests/section.ts`        | **The request shape.** Leave and expenses are both built from it          |
| `src/data/requests/sections.ts`       | The three request sections, as the sidebar and the tab switcher read them |
| `src/data/requests/`                  | Leave, expenses and procurement — one module per section beside the shape |
| `src/data/selfService.ts`             | The profile pages, driven entirely by the server's record registry        |
| `src/data/workflowStyle.ts`           | **The styling vocabulary.** A Workflow State's style → a badge or button  |
| `src/components/RequestGate.vue`      | The permission preamble every request page opens with                     |
| `src/components/EmployeeRequired.vue` | The two empty states for a login with no employee record                  |
| `src/data/session.ts`                 | The session user, from boot data or `commons.api.get_session_user`    |
| `src/components/LinkControl.vue`      | Link-field picker backed by Frappe's own link search                      |
| `src/pages/`                          | Announcements, profile, and a "mine"/"approvals" pair per request section |

## One app, several sections

The desk shows one icon, **Commons**, and behind it is one app, read by a
member of staff about themselves. Everything in it is something a
person raises about themselves and waits on an approver for: their profile,
their bank accounts, their leave, their expenses, their purchases.

`src/data/apps.ts` stays a registry with a single entry rather than being
dissolved into the router. It is what `meta.app` points at, what the header
names, and what the desk apps screen mirrors — and a second app would be an
entry there rather than that structure being rebuilt. An `Employees` directory
used to be the other one.

The sections inside it are two things:

- **Self-service** (`/profile/:slug`) — one page per record type the server's
  registry offers. Adding a record type is a desk entry and no frontend change.
- **Requests** (`/leave`, `/expenses`, `/procurement`) — each one page with two
  tabs, *what I raised* and *what I have to decide*. The tabs stay two routes,
  so a queue can be linked to and a reload comes back where it was;
  `src/data/requests/sections.ts` holds the half the sidebar and the tab
  switcher both need.

### How the desk icons work

The desk renders **`Desktop Icon` documents**, not a hook. This app ships one as
a file, `commons/desktop_icon/commons.json`, which `frappe.model.sync` imports on
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

## Requests

Leave, expenses and procurement are one shape wearing three names, and the
server says so: `commons.requests.approvals` holds the decision vocabulary,
the queue and its badge, the permissions payload and the decide-or-apply-workflow
transaction, and each section supplies only its doctype, its deciding field and
the rules HRMS applies to it and not the others.

The browser mirrors that split. `src/data/requests/section.ts` is a factory:
leave and expenses are both built from it, so a permissions call, the employee
behind the session, your own list, an approvals queue with per-row buttons and a
label for each row are written once. Procurement keeps its own module, because
its queue is grouped by the department whose budget it spends and its
permissions payload answers a different question — workflow access, not an
approve right.

Nothing on these pages names a status, a role or an outcome. Where a site runs a
Frappe Workflow, the states, their styling and the transitions a given user may
take all arrive from it; where one does not, the outcomes are read off the
deciding field's own options. `workflowStyle.ts` is the only place that turns
the site's styling vocabulary into a colour.

All three are optional, and each is absent for its own reason. `required_apps`
names nothing at all: leave and expenses are HRMS doctypes end to end, and
procurement spends against a Company, orders Items in a UOM and hands over to a
Material Request, so it needs ERPNext. A site running bare Frappe gets this app
with self-service, announcements, workspaces and the permission gate, and none
of the three.

Nothing in the browser knows any of that. The permissions endpoint for a section
this site cannot run answers `read: false`, which is the same answer it gives a
user who may not read one — and that is what already hides the sidebar row, the
tabs, the badge and the search bar's "New leave request". The server drops the
navigation rows too (`shell.pages.available`, which asks the section rather than
restating it), so the desk's Awesome Bar does not offer a page that is not
there, and every endpoint behind a missing section refuses rather than 500s.

`approvals.RequestType.available` is the one question all of this comes down to,
and `commons.commons_core.apps` is why it is asked two ways: leave and expenses name a
doctype, because that doctype is the whole of what they touch, while procurement
names ERPNext, because its own doctype is this app's and would answer yes on a
site where nothing about the section works.

### Leave

Two pages over HRMS's `Leave Application`:

- **My leave** — the signed-in user's own balances and requests, and the
  request form. Self-service, so it resolves the employee by
  `Employee.user_id`; a login with no employee record is told who to ask, and
  which of the two reasons applies.
- **Approvals** — requests naming the signed-in user as `leave_approver`,
  with Approve / Deny.

A decision is two writes underneath — `status` (which sits at permlevel 1) and
a submit — so `commons.requests.leave.decide_leave_application` does both in
one transaction. The endpoint requires the caller to be the application's
*named* approver, or hold a role that owns the doctype: the `Leave Approver`
role by itself grants submit on every leave application, which would let one
team's supervisor decide another team's requests.

Balances, day counts and every validation (overlaps, allocation periods,
maximum continuous days) come from HRMS rather than being recomputed here, so
what the form shows is what gets booked.

#### What leave needs configured

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

### Expenses

The same two pages over HRMS's `Expense Claim`, with two differences that are
the section's own:

- a claim is money, so what it is priced at, which cost centre it is charged to
  and which account each expense books to are settled by
  `request_expense_claim` rather than collected by the form;
- an approver may allow less than was claimed, and those per-row figures travel
  with the decision in one call, so the amount and the outcome land together.

### Procurement

`Procurement Request` is this app's own doctype and has been driven by a Frappe
Workflow from the start. Its approvals page is grouped by department, with the
budget each group spends priced beside it — see `docs/department-budgets.md`.

## Permissions

Every section fetches a permissions payload (`get_leave_permissions` and its
siblings) and the UI hides or disables what the user cannot do. That is a
courtesy, not the boundary: every read and write goes through the REST API,
which applies the same checks server-side. Lists the pages fetch for themselves
go through Frappe's document API precisely so that role permissions, User
Permissions and this app's own gate in `commons.safer_permissions` all apply
without the frontend restating any of them.
