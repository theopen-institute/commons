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
yarn test        # vitest, over the pure modules under src/data
yarn build       # writes ../commons/public/frontend + ../commons/www/commons.html
```

`yarn test` covers the modules under `src/data` that fetch nothing —
`attendanceRegister.ts` is the one so far. Those are the parts that are
arithmetic rather than plumbing, and the attendance register's were a Python
test suite before the reads moved to the document API; see
[Attendance](#attendance). It runs off `vitest.config.ts` rather than
`vite.config.js`, which loads `frappe-ui/vite` and reads the bench.

`yarn build` is what makes `/commons` work on the site: it copies the built page
to `commons/www/commons.html`, which `website_route_rules` in `hooks.py` points
every `/commons/*` path at.

## Layout

| Path                                  | What it is                                                                |
| ------------------------------------- | ------------------------------------------------------------------------- |
| `src/App.vue`                         | `DesktopShell` — sidebar plus the routed page                             |
| `src/data/apps.ts`                    | **The app registry.** Which apps exist and who may open them              |
| `src/components/AppSidebar.vue`       | Per-app navigation, app switcher, theme toggle                            |
| `src/data/statement.ts`               | **Account Balance.** The reader's own ledger and loan balances            |
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
- **Account Balance** (`/account`) — a statement rather than a request: what
  this person owes the organisation and what it owes them. One page, one call,
  no approvals tab. See [Account Balance](#account-balance).
- **Bank Reconciliation** (`/banking`) — a bank account's statement, line by
  line, with loan repayments booked from deposits. See
  [Bank Reconciliation](#bank-reconciliation).
- **Document Capture** (`/capture`) — a scanned supplier's invoice, read by
  Claude and drafted as a Purchase Invoice with the scan attached. See
  [Document Capture](#document-capture).
- **Attendance** (`/attendance`) — the one section addressed to somebody in
  their capacity as staff rather than as a person with a payslip: a term of a
  course, and who was at it. Nothing is raised and nobody approves it, and it
  adds no server endpoint of its own. See [Attendance](#attendance).

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

## Account Balance

`/commons/account` — the one section here that nobody raises anything in. It
answers "what is on my account", and the argument for every part of it is in
`commons/statement/__init__.py`. Three things are worth knowing from the
browser's side.

**Fees, invoices, payments and journal entries are one list, not four.** Every
one of them posts a `GL Entry` against the party, so the ledger is the
statement — which is why a site that installs Education gets its `Fees` on this
page without a line changing, here or on the server.

**Loans are a second balance, and never added to the first.** Not presentation:
`lending` posts its GL entries with the borrower as the party, so a loan's
principal sits in the same table as the invoices and would be summed with them
by anything filtering on the party alone. On real data that turned a settled fee
account into one reading NPR 120,000 owed. The server takes the lending module's
accounts out of the ledger and answers for them separately, and nothing in
`statement.ts` or on the page adds the two together.

**There is no permission preamble.** `RequestGate` gates on a permissions call,
and there is nothing here to permit — no approving, no creating. The page gates
on three empty states instead, because they send the reader to three different
people: no ledger on the site, no party record in your name, or an account with
nothing on it. The row is in the sidebar for everyone, on the same reasoning as
a self-service row: a page saying "you have no account here" explains an empty
balance better than a missing row does.

### The same statement as a PDF

`commons/statement/install.py` creates one `Print Format` per party doctype the
site has — Customer, Student, Supplier, Employee — and each is a two-line stub:

```jinja
{%- set statement = party_statement(doc.doctype, doc.name) -%}
{% include "commons/statement/print/statement.html" %}
```

`party_statement` is the app's own endpoint, reachable from Jinja through the
`jinja` hook in `hooks.py`. So the printed statement asks the app what somebody
owes rather than working it out again in a template: which way a balance runs,
which accounts are left out because they belong to the lending module, how a
running balance reconciles with a total — all of it answered once, in Python,
for both renderers.

Which is why `direction` is a field on the payload rather than something this
frontend derives. It used to be derived here, from the sign and the account
type, and that is exactly the kind of small derivation that gets written a
second time the moment the same page is wanted as a document. The server says
which way a balance runs; `statement.ts` and `print/statement.html` each only
choose the English for it, and they word it differently on purpose — one is
addressed to the reader, the other may be read by whoever was handed it.

Each account on the page carries a **PDF** link to
`commons.statement.api.download_statement`, which renders that same print format
for a reader who has no desk to print from.

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

## Attendance

`/attendance?term=…&course=…` is one term of one course, for every student group
taught it: sessions down the side, students across the top, one mark in each
cell. It replaced a Vue app embedded in a desk form.

**The grid is read-only.** Clicking a session's row, or any cell in it, opens
that session's details (`AttendanceMarksDialog`), and that dialog is the only
place a mark changes. Choices there are a draft: changed rows are highlighted,
the Save button says how many marks it will write, and while there are unsaved
changes an outside click or Escape does not close it. "All present" fills the
draft; it saves nothing on its own. Creating a session still offers "everyone
present", so taking attendance is a tick and then the exceptions. An earlier
version had cells that cycled Present → Late → Absent → blank and saved on every
click. That was quick, but a stray tap while scrolling on a tablet changed a
real record and nothing on screen showed it.

**The arithmetic is in `src/data/attendanceRegister.ts`**, which is pure and
tested (`yarn test`). What a late arrival is worth — half the session's hours —
is said once, in `CREDIT`, and the blocks and footings are built from it. That
matters because the version this replaced said it in a template and got the
group totals wrong in a way nobody could see: it footed the *first* group's
hours under every group on the page.

**Nothing here has an endpoint of its own.** An earlier version of this page
assembled the whole register in one custom API and answered in a single call,
which read nicely and was wrong: to do it the server had to read six tables with
`frappe.get_all`, which is `ignore_permissions=True`, so it walked past User
Permissions and past `commons.safer_permissions` — the gate whose entire purpose
is that a role grants nothing until a User Permission narrows it. A single
"may this person mark attendance" check at the door is not a substitute for that.

So the page reads through `/api/v2/document/<doctype>` and writes through
`frappe.client` (`insert`, `insert_many`, `set_value`, `delete`), exactly as the
section below describes for everything else. The cost is four chained rounds of
reads instead of one call — a course reaches its groups only through
`Program Course`, sessions are read for the groups that came back, marks for the
sessions that came back. That is what correctness costs here, and it is the same
bargain the rest of this app makes.

Two of Frappe's shapes are used rather than one, and the split is not arbitrary:
`Program Course` and `Student Group Student` are child tables, and the REST
document API cannot read one usefully — `document_list` never passes a
`parent_doctype` to the query engine, so a child doctype is permission-checked
against its own empty permissions and every requested field is stripped, leaving
a list of bare `name`s. Those two go through `frappe.client.get_list`, which
takes `parent` and is what the desk uses for the same job.

Whether this reader may mark attendance is asked with
`frappe.client.has_permission`, not with an endpoint of this app's. Whether the
*site* has a register at all is not asked at all: `commons.shell.pages.available`
already drops the row from every workspace on a site with no education module,
so a row that is there is a register that exists.

### What attendance needs configured

The section is absent without the education module — `Course Schedule` and
`Student Attendance` are what it is made of. Beyond that it stands on four
Custom Fields this app ships as fixtures
(`commons/fixtures/custom_field_education.json`): a session's type and details, the
`custom_late` flag, and `custom_inactive` on `Academic Term` for retiring a term
from the picker. `custom_session_type` is free text on purpose — the vocabulary
is the school's, the dialog offers whatever is already in use, and a fifth kind
of session is somebody typing it once rather than a deploy.

A `Course` wants a `default_instructor` and a default classroom: `Course
Schedule` requires both and the site fetches them from there, and this page
deliberately sets neither rather than overriding a school's answer with a guess.

Unlike the other sections, the sidebar row is **gated**: `Student Attendance` is
readable by every student and guardian on the site, and the register is a whole
cohort's marks on one screen. It is offered to whoever may *write* a mark. See
`commons.education_extensions.attendance.can_mark`, which the navigation and the
desk's Awesome Bar ask, and which the browser asks for itself.

## Bank Reconciliation

`/banking?account=…&from=…&to=…` is one company bank account's statement lines
for a period, in place of the desk's Bank Reconciliation Tool. The tool's
server functions are sound and every write here but one is one of them
(`src/data/reconciliation.ts` lists them). The page keeps the modal rule: the
list is read-only, a line opens a dialog, and each tab there (loan repayment,
match existing, payment entry, journal entry, details) holds a draft with its
own button. A write closes the dialog, and a toast links to the document it
created or matched.

**The period's figures.** Under the account and the dates, four figures:
opening and closing balance as per books (ERPNext's cleared balance), the
bank's closing balance recorded on or before the period's end, and the
difference. The account picker says how far the statement has been imported.

The "to reconcile" view shows both halves of what is left side by side:
statement lines with no entry, and entries with no statement line (read
from ERPNext's Bank Reconciliation Statement report). Likely pairs (same amount,
same direction, nearest date) are flagged. Dragging one onto the other, or
pressing Match on a likely pair, opens a confirm dialog, and ERPNext's
`reconcile_vouchers` runs on Save. A note says when open items fall outside
the dates, and "Show them" adds them to the board without moving the dates.

"Include drafts" adds unsubmitted vouchers that will post to the bank's account
when submitted: Payment Entries, Journal Entries, paid Purchase Invoices, POS
Sales Invoices, and lending's repayments and disbursements. They are read
whatever the period, marked as drafts, and left out of the column total,
because they are not in the ledger. A line paired with a draft is
matched by `commons.banking.reconciliation.submit_and_reconcile`, which
submits the draft as it stands and matches it in one transaction.

**Make draft.** The loan repayment, payment entry and journal entry tabs each
have a "Make draft" button beside the one that creates, submits and
reconciles. It creates the same document, with the same checks and
dimensions, as a draft: nothing is posted and the line stays open. Drafts show
up on the board under "Include drafts", where "Submit and match" finishes them.
A loan repayment is saved with the day the money arrived as its posting date.
Lending replaces that with "now" on every save, and two server scripts on the
site ("Loan Repayment - Remember Posting Date" and "... - Keep Posting Date")
put it back. Without them, repayments post on the day they are booked. Loan repayment drafts
go through `create_loan_repayments(draft=True)`, and payment and journal entry
drafts through `frappe.client.insert`.

**What a payment is booked against.** Once a party is chosen, the payment
entry tab lists their outstanding invoices, fees and other documents, from
ERPNext's own `get_outstanding_reference_documents`, the call behind the desk's
"Get Outstanding Invoices". Each has an amount to allocate, pre-filled
(`src/data/paymentAllocation.ts`, tested): the one document whose outstanding
is exactly the payment, or else oldest first. What is left is booked as an
unallocated advance. The allocation goes on the entry's references table,
whether it is created or drafted.

**Accounting dimensions.** The payment and journal entry tabs ask for every
accounting dimension the company makes mandatory (on register.localhost,
Department, for both Profit and Loss and Balance Sheet accounts), with the
company's default filled in. The bank's own line is a Balance Sheet account,
so on such a company every entry needs it. Which dimensions are mandatory comes
from `commons.banking.reconciliation.accounting_dimensions`, because Accounts
Users may not read `Accounting Dimension`. Journal entries go through ERPNext's
`create_bank_entry_and_reconcile` with the dimension on both lines. Payment
entries are built by `create_payment_entry_bts` (`allow_edit`), given the
dimension, and submitted by `create_payment_entry_and_reconcile`.

**Importing a statement.** "Import statement" takes the bank's export (XLSX,
XLS, CSV), the statement as a PDF, or photos of its pages, and reads it in
`commons.banking.statement_import`. A spreadsheet is read in code once Claude
has named its columns from a sample, so no figure is copied by a model. A PDF
or photo is copied row by row by Claude, the way Document Capture reads
invoices. The reading runs in a background job (the `long` queue, up to ten
minutes), because copying a long PDF can outlast a web request. Claude's answer
is streamed, and the dialog polls every two seconds and shows how many rows have
been copied so far. The dialog then proposes each row (`src/data/statementImport.ts`,
tested): rows with the same date, direction and amount as a line already on the
account are unticked as already imported. A line up to three days away counts
only if the description agrees too, and lines are paired off one each. Rows
whose running balance does not follow from the row before are flagged. "Import"
inserts and submits the ticked rows through `frappe.client.insert_many`, 200 a
request. It needs a Claude key in Claude Settings, as Document Capture does,
and create on Bank Transaction.

**Loan repayments.** For a deposit, the dialog suggests the borrower and says
why: the party on the line, the borrower's name in the description, or an
account or phone number seen on their earlier repayments. The logic is in
`src/data/reconciliationRules.ts`, tested by `yarn test`, together with how it
scored against register.localhost's history. Booking goes through
`commons.banking.reconciliation.create_loan_repayments`, which makes the same
Loan Repayment the desk would and matches it in one transaction. A deposit can
be split across several loans.

**What it needs configured.** Lending 16 refuses every Loan Repayment until a
Loan Demand Offset Order is set on the Loan Product or the Company. The Loan
Product's repayment account has to be the bank's GL account; if it is not, the
endpoint refuses before submitting. Lending's own bank-rec matching query is
broken upstream (it returns no `rank`), so uncleared repayments are read and
ranked by the page instead.

The row is gated on write on `Bank Transaction`. ERPNext's candidate search
(`get_linked_payments`) reads vouchers without a permission check, so the page
is only offered to whoever keeps the books.

## Document Capture

`/capture` takes a photo or PDF of a supplier's invoice and drafts a Purchase
Invoice from it. The server side is `commons.document_capture.purchase_invoice`
(read, suggest, preview, create), and the scan is read by
`commons.api_integrations.claude`.

The page writes nothing. Choosing a scan sends it to be read, and nothing is
stored at that point. The dialog then shows the scan beside the draft, with the
reason for each suggestion: the supplier (by tax number or name), each line's
expense account (from this company's earlier invoices), and the taxes (from
this supplier's last invoice, or a template). The totals are ERPNext's own, from
`preview`, and they are compared with the total printed on the scan. "Create
draft invoice" inserts it as a draft, making the supplier first if asked, and
then attaches the scan through Frappe's upload. Nothing is submitted.

Bikram Sambat dates come back as printed and are converted in
`src/data/captureRules.ts` with the date picker's tables, which `yarn test`
covers.

**What it needs configured.** An API key in **Claude Settings** (System Manager
only). Without one the row is left out. The model defaults to `claude-opus-5`.
Each read costs a few cents, and each person is limited to 60 reads an hour.

The row is gated on create on `Purchase Invoice`, the same test the endpoints
make before anything is sent to Claude.

## Permissions

Every section fetches a permissions payload (`get_leave_permissions` and its
siblings) and the UI hides or disables what the user cannot do. That is a
courtesy, not the boundary: every read and write goes through the REST API,
which applies the same checks server-side. Lists the pages fetch for themselves
go through Frappe's document API precisely so that role permissions, User
Permissions and this app's own gate in `commons.safer_permissions` all apply
without the frontend restating any of them.
