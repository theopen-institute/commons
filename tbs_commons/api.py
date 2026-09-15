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
