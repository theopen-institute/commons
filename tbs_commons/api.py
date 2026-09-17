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
	`get_list` would raise: several callers are permission endpoints that must
	not 500 on the way to saying what a user may do.

	`None` is therefore two answers in one -- "there is no record" and "there is
	one and you may not see it" -- which is fine for a caller that only wants the
	record and wrong for one that has to explain its absence. `session_employee_access`
	is that explanation; a page that renders an empty state should ask it.
	"""
	if not frappe.has_permission(EMPLOYEE, "read"):
		return None
	rows = frappe.get_list(
		EMPLOYEE,
		filters=session_employee_filters(),
		fields=fieldnames,
		limit_page_length=1,
	)
	return rows[0] if rows else None


def session_employee_filters() -> dict:
	"""What makes an Employee row this session's own.

	One definition, because `session_employee` and `session_employee_access` have
	to agree: a discriminator that looked for a different row than the read did
	would report `forbidden` for a record that was never a candidate.
	"""
	return {"user_id": frappe.session.user, "status": "Active"}


def session_employee_access() -> str:
	"""Why there is no employee record to show, when there is not one.

	`visible`, `forbidden` or `missing`. The same three answers self-service
	settled on for the same reason -- see `self_service.api._record_access`,
	whose docstring is the argument for all of this: "you have no record" and
	"you may not see your record" send the reader to different people, HR for the
	first and whoever administers permissions for the second, and a page that
	cannot tell them apart has to guess.

	Leave had exactly the failure that docstring warns about. `session_employee`
	returns `None` for both, so a user whose `Employee` read was revoked -- or who
	is caught by this app's own gate in `tbs_commons.safer_permissions` -- was
	told their login was not linked to an employee record and sent to HR to
	create one that already exists and already names them.

	The existence test is a raw read, and deliberately so: it returns a boolean,
	never record data, so the only thing it can disclose is that somebody has
	created a row against the caller's own login. That is the same bounded
	disclosure `registry.record_exists` makes, and it is the whole point -- a
	permission-checked test cannot distinguish the two cases, because being
	refused is one of them.

	An employee marked `Left` reads as `missing` rather than `forbidden`, because
	the filters apply to both halves. That is the honest answer: nothing is
	withholding the record, it has stopped being theirs.
	"""
	if frappe.has_permission(EMPLOYEE, "read") and frappe.get_list(
		EMPLOYEE, filters=session_employee_filters(), pluck="name", limit_page_length=1
	):
		return "visible"
	return "forbidden" if frappe.db.exists(EMPLOYEE, session_employee_filters()) else "missing"


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_approvers(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
) -> list[tuple[str, str]]:
	"""HRMS's own approver query, with the approver's name in one column.

	Who may approve is HRMS's answer and stays HRMS's answer -- the employee's
	own approver, then every approver named up their department tree. This adds
	nothing to that and takes nothing away.

	What it changes is the shape. HRMS returns `(user, first_name, last_name)`,
	and Frappe joins every column after the first with a comma to make a link
	option's description (see `build_for_autosuggest`), so a picker offered
	"Alice, Art-Head" -- a person's own name read as a list of two things. One
	column, one name, no comma.
	"""
	from hrms.hr.doctype.department_approver.department_approver import (
		get_approvers as hrms_approvers,
	)

	rows = hrms_approvers(doctype, txt, searchfield, start, page_len, filters)
	# Sorted, because HRMS answers with a set: the picker would otherwise put
	# the same candidates in a different order on every keystroke.
	return sorted((row[0], " ".join(part for part in row[1:] if part)) for row in rows)


def department_head(department: str | None) -> str | None:
	"""The first approver a department lists -- its head, as far as spending goes.

	A disabled department is not an answer, and neither is a department with an
	empty table: the caller gets `None` and the form opens blank so the requester
	picks.
	"""
	if not department:
		return None
	if frappe.db.get_value("Department", department, "disabled"):
		return None
	return frappe.db.get_value(
		"Department Approver",
		{"parent": department, "parentfield": "expense_approvers", "idx": 1},
		"approver",
	)


def default_expense_approver(employee: frappe._dict | None) -> str | None:
	"""Who an expense claim should name, before the requester touches the field.

	The employee's own expense approver first; failing that their department's
	head, which is how the desk's own Expense Claim decides it too -- see
	`hrms.api.get_expense_approval_details`.

	Expense claims only. Procurement deliberately names the department head and
	nothing else: a request spends the department's budget, so it is the
	department's head who decides it, whoever happens to sign off the requester's
	personal expenses.
	"""
	if not employee:
		return None
	if employee.expense_approver:
		return employee.expense_approver
	return department_head(employee.department)


@frappe.whitelist()
def get_session_user() -> dict:
	"""Return the session user, for the sidebar's account row.

	A production build gets this from the page's boot data; the Vite dev
	server serves index.html without the Jinja pass, so the SPA asks for it.
	"""
	from tbs_commons.www.tbs_commons import get_user_info

	return get_user_info()
