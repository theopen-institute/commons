"""Session-level endpoints for the TBS Commons frontend.

Domain endpoints live with their domain: `tbs_commons.procurement.api` and
`tbs_commons.procurement.budget` for procurement, `tbs_commons.leave.api` for
leave. What is left here is what belongs to no one section -- who is logged in,
and what they may do with the Employee directory.
"""

import frappe

EMPLOYEE = "Employee"

# What the frontend gates on. `submit`/`cancel` are absent because Employee is
# not a submittable doctype.
PERMISSION_TYPES = ("read", "write", "create", "delete")


def roles_with_permission(doctype: str, **ptypes: int) -> set[str]:
	"""Roles whose permission rows on `doctype` grant all of `ptypes`.

	Both sections ask a version of "who is allowed to do this", and both want the
	answer the site's own Role Permission Manager gives rather than a list of
	role names in Python. `permlevel` 0 unless a caller says otherwise: the
	higher levels gate individual fields, not the action.

	Custom DocPerm *replaces* the standard rows rather than adding to them, so a
	doctype with any customisation at all is answered from there alone -- falling
	back to `DocPerm` for a site that deliberately revoked something would hand
	back the permission it had just taken away.
	"""
	source = (
		"Custom DocPerm"
		if frappe.db.exists("Custom DocPerm", {"parent": doctype})
		else "DocPerm"
	)
	ptypes.setdefault("permlevel", 0)
	return set(frappe.get_all(source, filters={"parent": doctype, **ptypes}, pluck="role"))


def session_employee(fieldnames: list[str]) -> frappe._dict | None:
	"""The active Employee record linked to the session user, or None.

	Shared by both sections: leave starts from "which employee am I", and
	procurement reads the same record for a department and an approver. One
	query rather than a name lookup followed by a fetch -- `get_value` takes
	filters and a field list together.
	"""
	return frappe.db.get_value(
		EMPLOYEE,
		{"user_id": frappe.session.user, "status": "Active"},
		fieldnames,
		as_dict=True,
	)


@frappe.whitelist()
def get_employee_permissions() -> dict[str, bool]:
	"""Return the session user's doctype-level permissions on Employee.

	The frontend uses this to decide what to render — a create button, an
	editable form, a delete action. It is a UI hint only: every write still
	goes through the REST API, which runs the same checks server-side.
	"""
	return {
		ptype: bool(frappe.has_permission(EMPLOYEE, ptype))
		for ptype in PERMISSION_TYPES
	}


@frappe.whitelist()
def get_session_user() -> dict:
	"""Return the session user, for the sidebar's account row.

	A production build gets this from the page's boot data; the Vite dev
	server serves index.html without the Jinja pass, so the SPA asks for it.
	"""
	from tbs_commons.www.tbs_commons import get_user_info

	return get_user_info()
