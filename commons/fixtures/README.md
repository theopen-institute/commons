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
| `custom_field.json` | The ten fields this app adds to Frappe's own doctypes, the eight on Email Template, and the derived fields it adds to its own |
| `custom_field_education.json` | The four fields the attendance register adds to Education's doctypes |
| `custom_field_erpnext.json` | The four fields the requests section adds to ERPNext's doctypes |
| `property_setter.json` | The image and title fields of this app's member doctypes |

All of the Custom Fields are schema: code dereferences every one of them, and
the part of the app that reads them does not work without them. Order within a
file matters where one field's `insert_after` names another.

## Fields for apps a site may not have

Education and ERPNext are optional, so their fields are in files of their own,
and a site without the app skips that file whole. What makes that work, as of
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

**`Website Settings.website_button_url`** — where the desk's "Website" button
opens. A Custom Field rather than a fork of Website Settings: the target of a
button is site configuration, and carrying a patched core doctype to say so
would mean re-patching it on every Frappe release. Read by
`commons.commons_core.website_link`, which serves it through `extend_bootinfo`
so the sidebar does not have to fetch a setting before it can render.

**`Role.home_page_priority`** — which role's Home Page wins when someone holds
several that each name one. Core picks whichever role the database returned
first; `commons.commons_core.home_page` orders them by this instead. Sits
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

**The Form Button tab on `Email Template`** — `email_doctype`,
`email_condition`, `custom_recipient_fieldname`, `custom_sending_account`,
`attach_document_print` and `custom_print_format`, with a tab break and a
column break for the layout. What a template needs to say for a form to send
it in one step: which doctype's forms offer it, when, to whom, from which
account and with which print. Read by `commons.email_extensions`, which draws
the Email menu on those forms and fills the composer from them. Every one but
`email_condition` was first added by hand on the site the module was written
for, where the templates already carry values in them, and they keep the names
they were given there, `custom_` prefix and `custom_tab_break_ybjfo` included:
a fixture replaces a record by name, so a tidier name would have left the old
field standing beside the new one rather than replacing it. The recipient
field is an Autocomplete rather than the Data it started as, so the form can
offer the doctype's address and link fields; both are the same column.

### This app's own doctypes (`custom_field.json`)

**The Member Details section on `Faculty`, `Associate Faculty` and `Fellow`** —
first, middle, last and full name, image, alternate email address and phone
number, each a derived field reading through `member_id` from the Member the
record is about. Custom Fields on this app's own doctypes, which is unusual, and
the reason is that a derived field can only be one: `derived_from` lives on
Custom Field (see above). The same nine rows on each doctype: a section and a
column break for the layout, and seven derived fields. The image is hidden on
the form, where it shows as the doctype's image instead (`property_setter.json`).
Nothing is stored, so the Member stays the one place a name or phone number is
kept. Empty until "Enable Derived Docfields" is ticked in Commons Settings,
which the section says once, in its description, rather than every field
saying it; the fields are still created on a site that hasn't, and the check
that would refuse a new derived field while the switch is off stands aside for
a migrate.

### Education (`custom_field_education.json`)

What the attendance register records that Education has nowhere to put. Read by
`commons.education_extensions.attendance`.

**`Course Schedule.custom_session_type`** — what kind of session it was. The
register groups by it and foots each group separately, because a term's seminar
hours and its field research hours are two different obligations and a single
total of them answers neither. Free text rather than a Select: the vocabulary is
the school's (this one runs four, another will run two), the register offers
whatever is already in use, and a Select would make adding a fifth a deploy.

**`Course Schedule.custom_session_details`** — what that session was actually
about, said in a few words beside the date.

**`Student Attendance.custom_late`** — that the student was there, but not at
the start. `status` has `Present`, `Absent` and `Leave` and nothing for it, and
it is not a fourth status: a late arrival *was* present, and every report that
counts attendance should keep counting them. What it changes is what the hour is
worth, which is the register's arithmetic and not the doctype's — see
`attendance.CREDIT`.

**`Academic Term.custom_inactive`** — that a term was run once and is not run
again. The term picker drops them; nothing else looks at it.

The `custom_` prefix is Frappe's mark of a site customisation rather than an
app's own field, and these are an app's. They keep it anyway: they were added by
hand on the site this register was written for, and there are thousands of rows
carrying them. A tidier name would be a rename, a patch, and a fortnight of
somebody's attendance quietly reading as nobody's.

### ERPNext (`custom_field_erpnext.json`)

**`Material Request.procurement_request`**, **`Material Request Item.procurement_request`**
and **`.procurement_request_item`** — back-references from the stock document to
the request it came from. They live on ERPNext's doctypes, so they are Custom
Fields rather than part of the `Procurement Request` definition.
`make_material_request` fills them in, and every read of a request counts back
through them to see what has actually been ordered — which is why the two on the
item rows are indexed.

**`Material Request.department`** — whose budget a request is charged to,
including on requests raised directly. Header-level and singular on purpose: one
request charges one department's budget. Note that enabling a Department
accounting dimension would add a separate per-row `department` to Material
Request Item, which is ERPNext's accounting attribution and not this.

## Property Setters (`property_setter.json`)

The image field of `Faculty`, `Associate Faculty` and `Fellow`, set to the
derived `image` above, so the form, list and link previews show the Member's
photograph. A Property Setter rather than `image_field` in the DocType's own
JSON, because core checks that a DocType's image field is one of its fields
whenever the DocType is saved, and in CI when it syncs too — before the Custom
Field it names has been imported. Its name, `<doctype>-main-image_field`, is the
one core gives this setting, so a site that pointed it somewhere by hand has
that record replaced rather than a second one added.

The title field of the same three, set to the derived `full_name`, so lists,
link fields and breadcrumbs show the Member's name rather than their ID. It is a
Property Setter for the same reason, and core also checks the title field when
it saves a DocType. The DocType JSON still says `member_id`. When "Enable Derived
Docfields" is off, queries leave `full_name` out rather than failing, and the
desk shows the record's name, which is the member ID. It does the same for a
record whose `member_id` is empty.
