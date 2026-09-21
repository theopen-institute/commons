"""Who may decide a request, and who a blank form names before anyone picks.

`approvals.py` next door is about the decision -- which outcomes exist, whose
queue a row is in, what pressing one writes. This is the narrower question of
*who*, and the answer is HRMS's throughout: an employee's own approver, then the
approvers named up their department tree. Nothing here adds a candidate HRMS
would not have offered or removes one it would.

It lives with requests rather than at the app root because every line of it is
about an employee and a department. The app root is for what the session is; a
department tree is not that.

All of it is optional. The fields and tables read here -- `Department Approver`,
and the `expense_approvers` table HRMS adds to ERPNext's `Department` -- ship
with HRMS, which is not in `required_apps`. On a site without it every function
here answers "nobody" rather than throwing, and the one caller that is not
itself HRMS-only (procurement's blank form, which pre-fills a department head)
simply opens with the field empty for the requester to pick.
"""

import frappe

from commons.api import session_employee_filters

DEPARTMENT_APPROVER = "Department Approver"

# The requests this app draws an approver picker for, and so the only ones
# `get_approvers` will answer about. HRMS's query also serves `Shift Request`,
# which this app has no form for -- and a whitelisted method is reachable
# without the page that names it, so what it answers for is written down rather
# than left to whatever a caller puts in `filters`.
PICKER_REQUESTS = ("Leave Application", "Expense Claim")


def installed() -> bool:
	"""Whether HRMS's approver tables are on this site.

	The doctype rather than the app, and cached, for the reasons
	`approvals.RequestType.available` gives. One check covers the whole module:
	`Department Approver` and the `Department.expense_approvers` table that
	points at it are written by the same `hrms.setup`, so a site has both or
	neither.
	"""
	return bool(frappe.db.exists("DocType", DEPARTMENT_APPROVER, cache=True))


def session_employee_name() -> str | None:
	"""The caller's own active Employee id, or None.

	A raw read, and narrowly so: it returns the caller's own id and nothing
	else, so the only thing it can disclose is that somebody has created an
	Employee row against the caller's own login. That is the same bounded
	disclosure `api.session_employee_access` and `expense._session_employee_name`
	make, and it is the right shape here for the reason that one gives -- a
	permission-checked read answers `None` for a user whose `Employee` access is
	gated, which would hand them an empty approver picker on a form they were
	nonetheless allowed to open.

	`session_employee_filters` rather than a bare `user_id`, so an employee who
	has left is not still picking approvers: one definition of what makes an
	Employee row this session's own, shared with every other reader of it.
	"""
	return frappe.db.get_value("Employee", session_employee_filters(), "name")


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_approvers(
	doctype: str, txt: str, searchfield: str, start: int, page_len: int, filters: dict
) -> list[tuple[str, str]]:
	"""HRMS's own approver query, with the approver's name in one column.

	Who may approve is HRMS's answer and stays HRMS's answer. This adds nothing to
	that and takes nothing away.

	What it changes is the shape. HRMS returns `(user, first_name, last_name)`,
	and Frappe joins every column after the first with a comma to make a link
	option's description (see `build_for_autosuggest`), so a picker offered
	"Alice, Art-Head" -- a person's own name read as a list of two things. One
	column, one name, no comma.

	Whose approvers, though, is this module's answer and not the caller's. HRMS's
	query asks no permission of any kind: it reads the `employee` named in
	`filters` with `frappe.get_value`, walks that employee's department tree,
	and -- when no approver is configured anywhere up it -- throws a message
	naming the employee and their department. So a caller who could choose the
	employee could name any id on the site and collect that person's name, their
	department and their approver chain, including for employees this app's own
	gate in `commons.safer_permissions` is withholding from them.

	The employee is therefore the session's, never the payload's -- the same rule
	`RequestType.request_employee` applies to the write, for the same reason, and
	the reason is the same one that makes a self-service form self-service. A
	payload naming somebody else is not refused here, only overruled: this is a
	link query feeding a picker, and a picker that threw would put a permission
	error under a search box.

	Note that a permission check is *not* what settles this, and cannot be.
	`procurement.get_procurement_approvers` gates on `create` because its query
	enumerates every holder of an approving role, which is a directory read that
	only a right can narrow. This query reveals nothing but the approvers of one
	employee, and `create` on `Leave Application` is held by every member of
	staff precisely so they can raise their own -- so gating on it would refuse
	nobody. Scoping the employee is the whole of the fix.
	"""
	# Only ever reached as the link query of a form this app draws for `Leave
	# Application` or `Expense Claim`, so HRMS is present by the time it is --
	# but a whitelisted method is reachable without the page that names it.
	if not installed():
		return []

	# Which request is being raised arrives in `filters`, not in `doctype`: that
	# argument is the link field's target, which is always `User`. HRMS reads it
	# from there too -- see its `filters.get("doctype")` branches.
	#
	# Normalised rather than trusted to be a dict. Through `search_link` it
	# always is, but this endpoint is reachable directly, where a GET's `filters`
	# arrives as a JSON string and could be a list. Anything that is not a dict
	# names no request, and no request means no picker.
	filters = frappe.parse_json(filters) if isinstance(filters, str) else filters
	if not isinstance(filters, dict) or filters.get("doctype") not in PICKER_REQUESTS:
		return []

	# The one thing the caller does not get to choose. `None` for a login with no
	# active employee record, which has no request to raise and so no approver to
	# pick; the form itself has already said so -- see `EmployeeRequired.vue`.
	employee = session_employee_name()
	if not employee:
		return []
	filters = {**filters, "employee": employee}
	# HRMS reads `department` from `filters` too, in preference to the employee's
	# own, which would put the scoping back in the caller's hands one field over.
	filters.pop("department", None)

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
	if not department or not installed():
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
	if employee.get("expense_approver"):
		return employee.expense_approver
	return department_head(employee.department)
