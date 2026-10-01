### Commons

Shared tools for Frappe

### Features

Features marked ⚙ are off until switched on in **Commons Settings**. The app ships no workflows, approval rules or roles beyond System Manager: who may use each doctype is granted in the Role Permission Manager, and processes are the site's own Frappe Workflows.

#### Commons frontend (`/commons`)

- **Staff web app**: a Vue SPA with a configurable sidebar, a workspace switcher, a user menu, notifications and a To Do panel.
- **Commons Workspaces**: named sections of the navigation (title, icon, logo, order, grouped rows), each made of shipped pages, self-service records, or links to any address on the site or beyond. A page belongs to one workspace only.
- **Landing page**: `/commons` opens the page Commons Settings names, or the first row each person may use.
- **Search**: Ctrl/⌘K searches the app's pages and the desk's doctypes together, and the desk's Awesome Bar finds the app's pages. Both offer only what the user may open.
- **Announcements** page (a placeholder for now, offered only where a workspace includes it).

#### Self service

- **Self Service Records**: a site declares which doctypes people can view as their own records (such as their Employee record), and which fields they may propose changes to.
- **Record Change Requests**: the owner proposes a correction and the responsible team approves or rejects it. The change is written under the approver's own permissions, and a field that changed in the meantime is refused. Without a Workflow, Commons Settings names the outcome that applies the change and whether reviewers may decide their own requests.
- **Account statement** (`/commons/account`): what a person owes the organisation and what it owes them, from the general ledger, with loans shown separately, a PDF per account, and a `party_statement` Jinja helper for print formats. Any Party Type whose record links to a User can be a statement party, and each Party Type can name its statement Print Format.

#### Requests and approvals

- **Leave** (needs `hrms`): your own leave applications, and an approvals queue.
- **Expense claims** (needs `hrms`): your own claims, and an approvals queue. Whether a claim naming no approver may be decided by any approver is a setting.
- **Procurement Requests** (needs `erpnext`): raise and track purchase requests, approve them through the site's own Frappe Workflow, and carry approved lines onto Material Requests. The app ships no workflow, states or approver rules; the approvals queue is grouped by whichever field Commons Settings names.

#### Banking and accounting (needs `erpnext`)

- **Bank Reconciliation** (`/commons/banking`): import a bank statement, match lines to vouchers, create draft vouchers or loan repayments from a line, and submit and reconcile in one step. **Bank Reconciliation Settings** hold the loan-matching weights and the repayment type.
- **Open Receivables / Open Payables** reports: what was open on a date and is still open today, as an account → party → voucher tree.
- **Payment Ledger Audit** report: where the payment ledger and the GL disagree (including refunds that Payment Reconciliation counts twice), with repairs.
- **Loan Date Audit** report (needs `lending`): lending GL entries that are not on their voucher's date, checks that the Loan vouchers on their own dates setting is in place, and repairs.
- ⚙ **Clearing internal transfers**: a Journal Entry whose bank and cash lines net to zero is cleared on its own posting date.
- ⚙ **Party on payable payment lines**: a Payment Entry's party is put on its tax and deduction lines to payable accounts, such as TDS.
- ⚙ **Payroll lines per employee** (needs `hrms`): a payroll run's accrual journal gets one line per employee, with their party, and their department where the company has a Department accounting dimension.
- ⚙ **Loan vouchers on their own dates** (needs `lending`): Loan Repayment, Write Off and Disbursement post on their own dates, not the date they were saved.

#### Document capture

- **Captured Documents** (`/commons/capture`): scans come in by upload or email. Claude reads them, but only when someone presses Read, in a background job. The prompts follow the company's country and currency and the Bikram Sambat setting, and Claude Settings' **Additional Instructions** and tax-term names add a site's own conventions. **Document Capture Settings** choose which kinds are captured, who sees each, a supervisor role, and extra legal-suffix words for matching suppliers.
- Drafts a **Purchase Invoice** from a supplier invoice (visible to the accounts team) or an **Expense Claim** from receipts (visible to the sender), with the scan attached.

#### Education (needs `education`)

- **Attendance register** (`/commons/attendance`): mark student attendance for your student groups, within your User Permissions. **Attendance Register Settings** names any fields the site has added for a Late mark (and what it earns), session types, details and hours, and retired terms, and say how student groups are found and whether Leave counts as absent or excused.

#### Email

- **Email menu on forms**: offers the Email Templates set up for that doctype and fills the composer from the chosen one.
- **MJML Email Templates**: templates can be written in MJML; each save compiles them to responsive HTML.
- **Notification with an Email Template**: a Notification can send an Email Template's content in place of its own message.
- **Delayed notifications**: a Notification's email can be held back for a while, and is not sent if the document is cancelled first.
- ⚙ **Visual HTML email editor**: the composer shows an HTML email as it will look and lets you edit it there.

#### Printing

- **Print templates**: write a print layout once as a Web Template, with declared inputs and Context Prep, and print it from several doctypes. Includes a Test PDF form.
- **QR codes**: a `make_qr_code` Jinja helper.

#### Desk navigation ⚙

- **Navigation rail**: a narrow rail of apps (Navigation Apps) beside the sidebar, plus Search, Notifications, To Do and Website.
- **User menu**: account, display, session defaults, site tools, help and logout, opened from your name in the sidebar.
- **Sidebar memory**: a reloaded page keeps the sidebar it was reached from.
- **Home page priority**: when a user holds several roles, the role with the lowest Home Page Priority decides where they land after login.
- **Desk To Do**: your open ToDos, next to the notification bell.
- **Desk islands**: shows Bank Reconciliation and Document Capture as desk pages (`/app/commons-banking`, `/app/commons-capture`) on Frappe v16.

#### Desk conveniences

- **Hide cancelled documents**: a per-browser toggle in the Display menu that hides cancelled records from every list-type view.
- ⚙ **Bikram Sambat calendar**: shows Date and Datetime fields in Bikram Sambat as well and adds a BS date picker, in the desk and in the Commons frontend. Values are still stored in Gregorian.
- ⚙ **Literal @ in desk URLs**: `/desk/member/name@example.org` instead of `%40`.
- **Clear site cache** without a terminal.

#### Data model and permissions

- ⚙ **Derived Docfields**: a Custom Field can show a value read live through a link (**Derived From**), as a real join in list, report and query views. Nothing is stored. Paths are checked on save and on migrate.
- ⚙ **Require User Permission gate**: a checkbox in the Role Permission Manager makes a role see no records until a User Permission narrows it. It applies to lists, documents, query reports, exports, prepared reports and Auto Email Reports.

#### Integrations

- **Claude**: an API key and model setting, and reading scanned documents into a JSON schema.
- **Google Workspace**: user accounts through domain-wide delegation: create, find, update, suspend, delete, passwords, aliases and photos.
- **Auth0**: user accounts through the Management API: create, find, update, delete, password-change tickets and verification emails.

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch develop
bench install-app commons
```

#### Optional apps

This app requires nothing but Frappe. Two of its sections need another app, and
a site without that app gets this one without the section rather than not at
all — the endpoints behind it refuse and its rows leave the navigation.

| Section | Needs |
| --- | --- |
| Leave, Expense Claims | `hrms` |
| Procurement | `erpnext` |

Install either alongside, in any order, and run `bench --site <site> migrate`.
Self-service, announcements, workspaces and the permission gate need neither.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/commons
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

none
