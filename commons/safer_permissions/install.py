# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Install and migrate hook for the gate: getting the checkbox in front of admins.

The gate column itself is two Custom Fields, one on each of the tables core keeps
role permission flags in -- `Custom DocPerm` and `DocPerm`. They are declared in
`commons/fixtures/custom_field.json` and written by Frappe's own fixture
sync, so nothing here creates them.

Deliberately not a `Permission Type`. That core extension point registers one
record per doctype, can only be written during install, migrate or developer
mode, and draws its checkbox among the rights. The gate applies to every doctype
and belongs beside "Only if Creator", so a plain column plus
`public/js/permission_manager_gate.js` is both simpler and closer to the truth.

That script is what this hook is left to deal with: appending it to a core page
is the one part of the arrangement Frappe will not re-deliver on its own.
"""

import frappe
from frappe.utils import now

PERMISSION_MANAGER = "permission-manager"


def sync_permission_manager() -> None:
	"""Make every desk drop its cached copy of the Role Permission Manager.

	`page_js` is appended to that page's script, and the desk caches the whole
	script in `localStorage` under `_page:permission-manager` with no version
	check at all -- `pageview.js` uses the key if it merely exists. The one thing
	that does invalidate it is `sync_pages()` at desk boot, which deletes the key
	when the Page's `modified` differs from the copy it cached alongside it.

	So touching the record is how a change to the gate checkbox reaches anyone
	who has opened this page before. Touched on every install and migrate rather
	than only when the script really changed: `with_page` fetches nothing until
	somebody navigates to the page, so the entire cost is one ~15KB request, paid
	by the few admins who open the Role Permission Manager, the first time they
	open it after a deploy. Comparing hashes to avoid that cost more code than
	the script it was guarding, and got it wrong in the direction that matters --
	a torn write leaves an admin holding a cached page with no gate checkbox on
	it, on the one page where the gate is configured.
	"""
	if not frappe.db.exists("Page", PERMISSION_MANAGER):
		return

	frappe.db.set_value("Page", PERMISSION_MANAGER, "modified", now(), update_modified=False)
