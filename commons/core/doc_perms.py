"""What the site's own permission rows say, read the way the desk writes them.

The Role Permission Manager writes `DocPerm` and `Custom DocPerm`, and every
section of this app ends up asking a version of "who is allowed to do this" --
who may decide a leave request, who may submit a procurement one. All of them
want the answer the site configured rather than a list of role names in Python,
and there is one rule about reading those two tables that is easy to get wrong
in each place separately.

Not to be confused with `commons.safer_permissions`, which is a third state
this app *adds* to those rows. This module only reads what is already there.
"""

import frappe


def roles_with_permission(doctype: str, **ptypes: int) -> set[str]:
	"""Roles whose permission rows on `doctype` grant all of `ptypes`.

	`permlevel` 0 unless a caller says otherwise: the higher levels gate
	individual fields, not the action.

	Custom DocPerm *replaces* the standard rows rather than adding to them, so a
	doctype with any customisation at all is answered from there alone -- falling
	back to `DocPerm` for a site that deliberately revoked something would hand
	back the permission it had just taken away.
	"""
	source = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": doctype}) else "DocPerm"
	ptypes.setdefault("permlevel", 0)
	return set(frappe.get_all(source, filters={"parent": doctype, **ptypes}, pluck="role"))
