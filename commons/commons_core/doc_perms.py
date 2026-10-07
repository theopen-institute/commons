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
	back the permission it had just taken away. The doctype's meta already holds
	the rows that way (`Meta.set_custom_permissions`), cached, so it is read
	from there. `frappe.permissions.get_doctype_roles` reads the same rows but
	asks about one right at any level, which is not this question.
	"""
	ptypes.setdefault("permlevel", 0)
	return {
		perm.role
		for perm in frappe.get_meta(doctype).permissions
		if all((perm.get(ptype) or 0) == value for ptype, value in ptypes.items())
	}
