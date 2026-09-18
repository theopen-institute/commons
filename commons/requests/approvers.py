"""Who may decide a request, and who a blank form names before anyone picks.

`approvals.py` next door is about the decision -- which outcomes exist, whose
queue a row is in, what pressing one writes. This is the narrower question of
*who*, and the answer is HRMS's throughout: an employee's own approver, then the
approvers named up their department tree. Nothing here adds a candidate HRMS
would not have offered or removes one it would.

It lives with requests rather than at the app root because every line of it is
about an employee and a department. The app root is for what the session is; a
department tree is not that.
"""

import frappe


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
