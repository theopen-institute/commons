# Fixtures

Records this app declares as data rather than creating from code. Frappe's
fixture sync imports every `.json` file in this directory on install and on
every migrate, in filename order — it globs the directory and does not read the
`fixtures` hook, which is only used by `bench export-fixtures` to generate files
from a site. These files are written by hand; do not run `export-fixtures`
against them.

Imports are `force=True`: each record is deleted and re-inserted on every
migrate, so **a site's edits to these records do not survive a deploy**. The
delete is `for_reload=True`, which skips `on_trash` — so for Custom Fields the
database column and everything in it are left alone, and only the definition is
rewritten.

| File | What it holds |
| --- | --- |
| `custom_field.json` | The ten fields this app adds to Frappe's core and customisation doctypes, the ten on Email Template, two on Notification, one on Communication, one on Email Account, and two on Web Template |
| `custom_field_erpnext.json` | The three fields the requests section adds to ERPNext's doctypes, and the financial reports' one on Account |
| `property_setter.json` | Which of Email Template's and Notification's own fields show when a template is designed in MJML or used by a Notification, and the fieldtypes a Web Template's inputs may have |

All of the Custom Fields are schema: code dereferences every one of them, and
the part of the app that reads them does not work without them. Order within a
file matters where one field's `insert_after` names another.

Every record names the module of the section that reads it. That is what takes
it away when the app is uninstalled: `remove_app` deletes every record linked to
one of the app's `Module Def`s, and a field left behind would sit on its form
promising behaviour nothing provides. Only the definition goes. Deleting a
Custom Field never drops its column, so the values stay in the database and
reappear when the app is installed again. A new record here needs a module too;
`test_fixtures` fails without one. See `commons.commons_core.uninstall`.

## Fields for apps a site may not have

ERPNext is optional, so its fields are in a file of their own, and a site
without it skips that file whole. Any other optional app's would be the same. What makes that work, as of
Frappe 16.34:

* fixture records are inserted with `ignore_links`, so the Custom Field's own
  Link to its doctype is not what fails;
* what fails is `CustomField.validate`, which loads the doctype's meta for a new
  field and raises `DoesNotExistError` when there is none;
* `frappe.utils.fixtures.import_fixtures` catches exactly that (and
  `ImportError`), prints `Skipping fixture syncing from the file …`, and goes on
  to the next file.

Two rules follow, and both matter:

* **One app per file.** A failing record stops its file there, but the records
  before it stay applied. A file holding one app's fields fails on its first
  record, so nothing of it lands; a file mixing apps would half-apply.
* **The skip depends on which exception comes first.** Were Frappe to change
  `CustomField.validate` so that some other error surfaced first, it would not
  be caught — it would escape into migrate's post-schema phase, which is atomic,
  and abort migrate for the whole site rather than skip a file.
  `commons.commons_core.test_fixtures` imports a fixture naming a doctype that
  does not exist, through Frappe's own `import_fixtures`, and fails if it is not
  skipped. Run it before taking a Frappe upgrade to production.

These fields used to be asserted by guarded install hooks, written when the
same missing doctype raised `LinkValidationError` — which is not caught, and did
abort migrate for the whole site. On Frappe 16.34 it no longer does; that was
checked against a site, and is what the test above keeps checking.

## Why each field exists

### Frappe's own doctypes (`custom_field.json`)

**`Website Settings.website_button_url`** — where the Commons sidebar's
"Website" button opens. A Custom Field rather than a fork of Website Settings:
the target of a button is site configuration, and carrying a patched core
doctype to say so would mean re-patching it on every Frappe release. Read by
`commons.better_navigation.website_link`; `www/commons.py` puts it in the
page's boot data so the sidebar does not have to fetch a setting before it can
render. The desk has no Website button since Frappe 16.50.

**`Role.home_page_priority`** — which role's Home Page wins when someone holds
several that each name one. Core picks whichever role the database returned
first; `commons.better_navigation.home_page` orders them by this instead. Sits
directly under the field it orders. Inert unless "Enable Home Page Priority" is
ticked in Commons Settings, which the field's description says.

**`require_user_permission`** on `Custom DocPerm` and `DocPerm` — the gate. A
role ticked here grants nothing until a User Permission exists for the user.
Both tables, because core reads `Custom DocPerm` instead of `DocPerm` once a
doctype has been customised. Not `DocShare`: sharing is out of scope, and core
re-grants around this app's hooks for a shared document anyway — see the
`commons.safer_permissions.permissions` docstring. Read by that module, and
drawn in the Role Permission Manager by `public/js/permission_manager_gate.js`,
which supplies its own translated label — so the `label` here is never shown to
anyone. The description is, in a DocType's own Permissions table, and says that
the tick is inert unless "Enable Require User Permission Gate" is ticked in
Commons Settings.

**`derived_from`**, **`derived_from_doctypes`** and **`derived_in_wildcard`** on
`Custom Field` and `Customize Form Field` — what makes a Custom Field a derived
field: the `link_field.target_field` it reads through, the doctypes a Dynamic
Link may point at, and whether `fields="*"` includes it. Custom Field is where
they are stored and where `commons.derived_docfields.registry` reads them; the
copies on Customize Form Field are only the grid's, carried to and from the
Custom Field by `commons.derived_docfields.extend_customize_form`, and hidden
for standard fields, which have a column and can't be derived. Not on
`DocField`: core never loads Custom Fields onto the doctypes that define
doctypes, so a derived field can only ever be a Custom Field. Each description
says the property is inert unless "Enable Derived Docfields" is ticked in
Commons Settings.

**The Form Button tab on `Email Template`** — `email_condition`,
`custom_recipient_fieldname`, `custom_sending_account`,
`attach_document_print` and `custom_print_format`, with a tab break and a
column break for the layout. What a template needs to say for a form to send
it in one step: when, to whom, from which account and with which print. Which
doctype's forms offer it is core's own `reference_doctype`, on the template's
first tab; each of these is shown only once it is set. Read by
`commons.email_extensions`, which draws the Email menu on those forms and
fills the composer from them. Every one but `email_condition` was first added
by hand on the site the module was written for, where the templates already
carry values in them, and they keep the names they were given there,
`custom_` prefix and `custom_tab_break_ybjfo` included: a fixture replaces a
record by name, so a tidier name would have left the old field standing beside
the new one rather than replacing it. The recipient field is an Autocomplete
rather than the Data it started as, so the form can offer the doctype's
address and link fields; both are the same column.

**`use_mjml`, `mjml_source` and `mjml_preview` on `Email Template`** — a
template designed in MJML: the switch, the source, and the place its live
preview is drawn. `commons.email_extensions.mjml` compiles the source into the
template's own `response_html` on every save, so what is sent is still a plain
HTML template and nothing that reads templates needs to know. Two Property
Setters go with them: `response_html` is hidden while the MJML is what gets
edited (it is the compiled output, and an edit to it would be overwritten by
the next save), and `use_html` is read-only while it has to stay ticked.

**`Notification.send_delay_minutes`** and **`.once_across_amendments`**, and
**`Communication.notification`** — a Notification's email held back, taken back,
and not repeated; read by `commons.email_extensions.scheduled` and
`commons.email_extensions.notification`. The delay holds the queued email that
long (the scheduler already honours `send_after`); "once across amendments"
skips a document amended from one already emailed about. Both matter for a
receipt sent on submit, where correcting a payment is cancel, amend, submit.
`Communication.notification` records which Notification an email came from, as
it is queued: nothing else tells a Notification's email from one somebody wrote,
and only a Notification's are the module's to take back or to count. Indexed,
since both of those look it up.

**The Print section on `Web Template`** — `print_section` and `context_prep`,
read by `commons.print_templates`. A Web Template is the one Jinja record a
site can keep that belongs to no doctype, which is what lets a layout be
printed from several doctypes' Print Formats through `render_web_template`.
The template's inputs are declared in core's own Fields table; `context_prep`
is the Python that turns them into the variables the layout reads, and the
section's description says how a Print Format passes them. A Custom Field
rather than a doctype of this app's own, so the layout, its inputs and its prep
are one record, edited on the form Frappe already has for it. A plain section,
not a collapsed one, so the description is in view. Test PDF's values are
deliberately not a field: they are often a real record's figures, and are kept
nowhere.

**`Email Account.capture_document_type`** — what the scans emailed to an
account whose Append To is Captured Document become: purchase invoices or
expense receipts. One account per kind, bills@ and receipts@ say, rather than
Claude guessing from the scan, which would be billed for and sometimes wrong.
Read by `commons.document_capture.capture.sort_email`. Shown only while the
account appends to Captured Document.

### Fields this app no longer ships

Removing a fixture file or record deletes nothing on a site: fixture sync only
imports. A field this app stopped shipping stays on a site that had it, as the
site's own Custom Field, until something removes it there.

### ERPNext (`custom_field_erpnext.json`)

**`Material Request.procurement_request`**, **`Material Request Item.procurement_request`**
and **`.procurement_request_item`** — back-references from the stock document to
the request it came from. They live on ERPNext's doctypes, so they are Custom
Fields rather than part of the `Procurement Request` definition.
`make_material_request` fills them in, and every read of a request counts back
through them to see what has actually been ordered — which is why the two on the
item rows are indexed.

**`Account.internal_account`** — which accounts record money moving between the
organisation's own departments. Read by `commons.banking.financial_statements`,
which leaves each such account, and everything under it, out of Profit and Loss
and the Gross and Net Profit Report when their Hide Internal Accounts filter is
ticked. That filter is only offered with "Enable Hiding Internal Accounts" ticked
in Commons Settings, so without it the field is inert. Which accounts are
internal is the site's to say, so the field is a fact about the account and not
a list in the settings.

## Property Setters (`property_setter.json`)

The two on `Email Template` go with `use_mjml`, above. On `Notification`,
Message and its examples are hidden while the Notification names an Email
Template: core's own `email_template` already hides Message and lifts
Subject's requirement then, but leaves the examples showing.

`Web Template Field.fieldtype`'s options, with Currency, Date, Float and JSON
added to core's list. A Web Template's Fields table is where
`commons.print_templates.contract` reads a print template's inputs, and core
offers only the types a website block is written with — text, images, a
checkbox — where a print's inputs can be amounts, dates or structured data.
Core's Web Page values editor draws all four with its own controls, so a
template used on a web page is unaffected.