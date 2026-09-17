"""Session-level endpoints and shared helpers for the TBS Commons frontend.

Domain endpoints live with their domain: `tbs_commons.procurement.api` and
`tbs_commons.procurement.budget` for procurement, `tbs_commons.leave.api` for
leave, `tbs_commons.self_service.api` for the profile. What is left here is what
belongs to no one section -- who is logged in, which employee record is theirs,
and which roles a doctype's own permission rows grant something to.
"""

import frappe

EMPLOYEE = "Employee"


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
	source = "Custom DocPerm" if frappe.db.exists("Custom DocPerm", {"parent": doctype}) else "DocPerm"
	ptypes.setdefault("permlevel", 0)
	return set(frappe.get_all(source, filters={"parent": doctype, **ptypes}, pluck="role"))


def session_employee(fieldnames: list[str]) -> frappe._dict | None:
	"""The active Employee record linked to the session user, or None.

	Shared by every section: leave starts from "which employee am I", procurement
	reads the same record for a department and an approver, and self-service
	reads it as the record being corrected.

	Through `frappe.get_list`, so the site's permissions decide what comes back --
	role permissions, User Permissions, and this app's own gate in
	`tbs_commons.safer_permissions`. The `user_id` filter narrows the query to
	this user's own row; it is not what makes the read safe, and is not trusted
	to be.

	This used to be `frappe.db.get_value`, which answers to no permission at all.
	The argument for it was that "may I read the Employee directory" and "may I
	read myself" are different questions -- which is true, and is an argument for
	configuring the second, not for answering it here in spite of the
	configuration. An administrator who gates the `Employee` role has said what
	they mean; a whitelisted endpoint handing the record over anyway makes that
	setting a decoration. Sites relying on the old behaviour want a User
	Permission on `Employee` whose `applicable_for` is `Employee` -- see the
	`safer_permissions` module docstring for why a blanket one does not count.

	`None` for a user with no read permission at all, rather than the throw
	`get_list` would raise: "you have no employee record here" is the same answer
	as far as every caller is concerned, and several of them are permission
	endpoints that must not 500 on the way to saying so.
	"""
	if not frappe.has_permission(EMPLOYEE, "read"):
		return None
	rows = frappe.get_list(
		EMPLOYEE,
		filters={"user_id": frappe.session.user, "status": "Active"},
		fields=fieldnames,
		limit_page_length=1,
	)
	return rows[0] if rows else None


@frappe.whitelist()
def get_session_user() -> dict:
	"""Return the session user, for the sidebar's account row.

	A production build gets this from the page's boot data; the Vite dev
	server serves index.html without the Jinja pass, so the SPA asks for it.
	"""
	from tbs_commons.www.tbs_commons import get_user_info

	return get_user_info()
