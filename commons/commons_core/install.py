"""App-level migrate hook: making the doctype sync see this app's modules.

Most of what this app adds to other apps' doctypes is declared rather than
created. Every Custom Field it adds -- to Frappe's doctypes, to ERPNext's, and
the derived fields on its own -- is under `commons/fixtures/`, written by
Frappe's fixture sync on install and every migrate; the ERPNext fields are in a
file of their own, which a site without ERPNext skips
(`commons/fixtures/README.md`). The Apps screen tile is the
`add_to_apps_screen` hook. None of that needs a hook of its own. The hooks left
in `hooks.py` do only what no sync can: this module makes sure the doctype sync
walks every module in `modules.txt`, and `commons.safer_permissions.install`
gets a changed `page_js` in front of admins whose desks still hold the last copy
of it. None of them creates a document a site would think of as its own.

Workflows and self-service configuration are a System Manager's to set up on
a new site, and the app ships none of them -- not as a seed, not as a fixture,
not at all. Property Setters are shipped only where they
belong to something else the app ships, in `commons/fixtures/property_setter.json`:

* two on Frappe's `Email Template`, hiding the compiled HTML and making
  `use_html` read-only while a template is written in MJML -- the other half of
  the MJML Custom Fields;
* one on Frappe's `Notification`, hiding the message examples while an Email
  Template is named -- the other half of `Notification.email_template`;
* one on Frappe's `Web Template Field`, adding the fieldtypes a print
  template's inputs may have.

The first three change Frappe's own forms only in ways that follow from a field
this app adds: each is inert until that field is set. The last applies
whenever a Web Template Field is edited.

`Module Def` records are core's business now: since 16.50,
`frappe.installer.sync_module_defs` runs at the start of every migrate, ahead
of the `before_migrate` hooks, and gives any module an app has added to
`modules.txt` since install its row. This module once did that itself, and
removed the rows of modules it had dropped; both are gone.

Why this is in `commons_core` and not at the app root
-----------------------------------------------------
`APP` is a fact about *the app*, and so is the hook below, and the module named
after the app is where facts about the app go. `commons.commons_core.uninstall`
reads `APP` from here.
"""

APP = "commons"


def refresh_module_map() -> None:
	"""Rebuild the module map before the doctype sync walks it.

	Which modules an app has is cached -- `frappe.setup_module_map` keeps the
	whole bench's map in Redis under `app_modules`, and the site's own under
	`installed_app_modules` -- and `frappe.model.sync.sync_all` walks
	`frappe.local.app_modules`, the copy `frappe.init` read from that cache,
	rather than `modules.txt`. A map cached before a new line was pulled into
	`modules.txt` therefore leaves the new module's `doctype/` folder unlooked
	in: the first migrate after the upgrade syncs everything except it,
	silently, and a second migrate puts it right.

	Migrate's own `setUp` calls `frappe.clear_cache()`, which deletes both keys
	from Redis but leaves `frappe.local.app_modules` as `frappe.init` built it,
	and nothing between there and the sync rebuilds it -- core's
	`sync_module_defs` writes the missing `Module Def` row but leaves the map
	alone. Dropping both keys and rebuilding here is what makes the first
	migrate enough. The deletes are not redundant with that `clear_cache`:
	`installed_app_modules` is written through `frappe.client_cache`, whose
	local copy invalidates on its own schedule.
	"""
	import frappe

	frappe.cache.delete_value("app_modules")
	frappe.client_cache.delete_value("installed_app_modules")
	frappe.setup_module_map(include_all_apps=True)
