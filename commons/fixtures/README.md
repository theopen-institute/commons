# Fixtures

Records this app declares as data rather than creating from code. Frappe's
fixture sync imports every `.json` file in this directory on install and on
every migrate — it globs the directory and does not read the `fixtures` hook,
which is only used by `bench export-fixtures` to generate files from a site.
These files are written by hand; do not run `export-fixtures` against them.

Imports are `force=True`: each record is deleted and re-inserted on every
migrate, so **a site's edits to these records do not survive a deploy**. The
delete is `for_reload=True`, which skips `on_trash` — so for Custom Fields the
database column and everything in it are left alone, and only the definition is
rewritten.

`custom_field.json` — the ten fields this app adds to core's own doctypes. All
ten are schema: code dereferences every one of them, and the app does not work
without them. Order in the file matters where one field's
`insert_after` names another.

## Why each field exists

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
