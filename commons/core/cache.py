# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Clearing this site's cache without a terminal.

`bench --site <site> clear-cache` is the usual way in, and it is no use to
somebody who has the desk but not the server -- which is most of the people who
notice a stale cache in the first place.

Frappe's own whitelisted `frappe.sessions.clear` is not that button. It is the
desk's Reload (and this app's, see `AppSidebar.vue`), and it clears the calling
user's session and user cache only -- the wrong tool whenever the stale thing is
shared rather than personal: a DocType's meta, a hook, a workspace, the assets
map that says which bundle the page should ask for.

`frappe.clear_cache()` with no arguments is the site-wide one. Per
`frappe.cache_manager`, that is every Redis key belonging to this site except
those apps have declared under the `persistent_cache_keys` hook, plus the
metadata version and the in-process caches.
"""

import frappe
from frappe import _

SYSTEM_MANAGER = "System Manager"


@frappe.whitelist(methods=["POST"])
def clear_site_cache() -> None:
	"""Clear the whole site cache. System Managers only.

	POST rather than a bare `@frappe.whitelist()`, which would answer a GET as
	well. Frappe's CSRF token is only checked on requests with a body, so a
	GET-able endpoint that changes server state can be fired by an `<img src>`
	on any page a System Manager happens to open. The cost of that here is a
	slow page rather than lost data, but it costs nothing to shut.

	Note that `frappe.only_for` lets Administrator through whatever its roles
	say -- that is core's rule for every `only_for` check, not a hole here.
	"""
	frappe.only_for(SYSTEM_MANAGER)
	frappe.clear_cache()

	# An alert rather than a modal: this reports that something routine
	# finished, and there is nothing for the reader to decide.
	frappe.msgprint(_("Cache cleared"), indicator="green", alert=True)
