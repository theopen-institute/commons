"""Who is using this app -- the one question every section starts from.

A request starts from "which employee am I", procurement reads the same record
for a department and an approver, and self-service reads it as the record being
corrected. That is what is left here: the session's own identity, and the
handful of ways it can be absent.

Nothing else. Domain endpoints live with their domain -- everything a person
raises and waits on an approver for is `tbs_commons.requests`, the profile is
`tbs_commons.self_service.api`, and anything that is really about Frappe rather
than about TBS is `tbs_commons.commons_core`. If something here stops being an
answer to "who am I", it belongs in one of those.
"""

import frappe

EMPLOYEE = "Employee"


def session_employee(fieldnames: list[str]) -> frappe._dict | None:
	"""The active Employee record linked to the session user, or None.

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
def get_session_user() -> dict:
	"""Return the session user, for the sidebar's account row.

	A production build gets this from the page's boot data; the Vite dev
	server serves index.html without the Jinja pass, so the SPA asks for it.
	"""
	from tbs_commons.www.tbs_commons import get_user_info

	return get_user_info()
