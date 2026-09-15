# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Role Permissions that grant nothing until a User Permission narrows them.

Frappe's two permission systems pull in opposite directions. Role Permissions
are additive: a role grants a right, and holding the role is enough. User
Permissions are subtractive: they remove rows from access a Role Permission has
already granted. Giving someone their own payslip and nobody else's therefore
means granting read on every `Salary Slip` in the company and then taking
almost all of them back, which leaves the sensitive half of the configuration
as the *second* step. From `frappe.permissions.has_user_permission`:

	user_permissions = get_user_permissions(user)
	if not user_permissions:
		# no user permission rules specified for this doctype
		return True

A User Permission that was never created, or was deleted, or whose automated
creation failed quietly, is indistinguishable from a user who was always meant
to see everything.

This module adds the missing third state, and adds it *per role*. A Role
Permission row may be marked `require_user_permission`; a role marked that way
grants nothing until a User Permission narrows it -- no rows in a list, no
document on a form, no report. Roles that should genuinely see everything are
left unmarked, so `Employee` and `HR Manager` can both hold read on `Salary
Slip` and mean entirely different things by it.

An unmarked role beats a marked one -- an HR Manager who also holds `Employee`
is an HR Manager -- but only when it is an unrestricted grant. A role marked
"Only if Creator" reaches the user's own documents and nobody else's, so it
cannot stand in for one: `Employee` carries that tick on doctype after doctype
and is held by nearly everyone a gated approver role would be drawn from, and
counting it would leave the gate ticked and inert. Such a role keeps exactly
what it grants -- the gate then withholds every row but the user's own. See
`gate_scope`.

None of this patches core. The marker is one Check field on `DocPerm`, `Custom
DocPerm` and `DocShare`, which the Role Permission Manager draws beside "Only if
Creator" -- see `safer_permissions.install.sync_gate_field`. Enforcement
is core's two permission hooks, both of which accept a `"*"` key so they are
consulted for every doctype, and both of which can only ever deny:

	has_permission                 one document: read/write/submit/print/...
	permission_query_conditions    list view, report view, `frappe.get_list`

Query and Script Reports honour neither hook -- they run whatever SQL the
report author wrote, and no amount of hooking makes that respect User
Permissions -- so gated roles are refused them outright. See
`run_query_report`.

Configured in one place: the Role Permission Manager, beside "Only if Creator".

The gate cannot demand a *particular* User Permission. That page renders
checkboxes and nothing else, so a role row has nowhere to name one. What it can
demand is that somebody pointed a permission at *this doctype on purpose*: a
User Permission whose `applicable_for` is the doctype being checked.

Blanket permissions are therefore ignored here, though core honours them. A User
Permission created without an `applicable_for` gets `apply_to_all_doctypes`, and
that is the default -- so counting them would mean one `Company` restriction,
created for some unrelated reason, silently satisfied every gate on the site.

This still cannot ask *which* link: a `Company` permission scoped to `Salary
Slip` opens that gate and shows every slip in the company. What it rules out is
opening a gate by accident, which is the failure that actually happens.
"""

import frappe

# `import frappe` alone does not bind the submodule, and `gate_satisfied` calls
# `frappe.permissions.get_user_permissions`. On a site something else has always
# imported it first, so the omission never showed; imported here so the gate does
# not depend on that.
import frappe.permissions
from frappe import _
from frappe.utils import cint

# The marker field. The Role Permission Manager labels a permission checkbox by
# title-casing its fieldname, so this reads "Require User Permission".
GATE = "require_user_permission"

# Reaching a document at all. A role that grants neither is not granting
# access this module could usefully withhold.
READ_RIGHTS = ("read", "select")

# Core's own row-scoping flag, drawn as "Only if Creator" directly above the
# gate. A role carrying it reaches the user's own documents and no others.
IF_OWNER = "if_owner"

# How far the gate holds a user back, once it applies at all.
NOTHING = "nothing"
OWN = "own"


def gated_doctypes() -> frozenset[str]:
	"""Doctypes where at least one role has the gate ticked.

	Memoised for the request. `gate_applies` is the first thing both hooks ask,
	on a path that answers every permission check on the site, so the common
	answer -- a doctype nobody has gated -- has to cost a set lookup rather than
	a role scan.

	Read with raw SQL on purpose. `frappe.get_all` would route through
	`DatabaseQuery`, which consults the very `permission_query_conditions` hook
	this function exists to serve; the sentinel below closes the same door twice.

	Not `site_cache`: that cache lives in one worker process and is not shared,
	so a gate ticked in one worker would stay invisible to the others until a
	restart. A silent hole in a permission check is not worth the saving.
	"""
	cached = getattr(frappe.local, "tbs_gated_doctypes", None)
	if cached is not None:
		return cached

	# Set before reading, so a re-entrant check terminates instead of recursing.
	frappe.local.tbs_gated_doctypes = frozenset()

	gated: set[str] = set()
	for table in ("Custom DocPerm", "DocPerm"):
		try:
			rows = frappe.db.sql(f"select distinct parent from `tab{table}` where `{GATE}` = 1")
		except Exception:
			# Before this app's first migrate the column is not there yet.
			continue
		gated.update(row[0] for row in rows if row[0])

	frappe.local.tbs_gated_doctypes = frozenset(gated)
	return frappe.local.tbs_gated_doctypes


def clear_gated_doctypes() -> None:
	"""Drop the request memo, so a tick is visible to the rest of this request."""
	frappe.local.tbs_gated_doctypes = None


def applicable_perms(user: str, doctype: str) -> list:
	"""The rows that grant `user` a read right over whole documents of `doctype`.

	Permlevel above 0 governs fields rather than rows, so core skips those rows
	when it decides which documents a user may reach, and so do we.
	"""
	roles = set(frappe.get_roles(user))
	return [
		perm
		for perm in frappe.get_meta(doctype).permissions
		if perm.role in roles
		and cint(perm.permlevel) == 0
		and any(perm.get(right) for right in READ_RIGHTS)
	]


def gate_scope(user: str, doctype: str) -> str | None:
	"""How far the gate holds `user` back on `doctype`.

	`None`     it does not: some ungated role grants unrestricted read.
	`OWN`      every unrestricted grant is gated, but an ungated "Only if
	           Creator" row still grants the user their own documents.
	`NOTHING`  every grant is gated.

	One ungated role is enough to see everything: an HR Manager who also holds
	`Employee` is an HR Manager. This mirrors how core resolves `if_owner`
	across roles in `get_role_permissions`, where an unrestricted grant beats a
	restricted one rather than intersecting with it.

	A role marked "Only if Creator" is not such a grant. It reaches the user's
	own documents and can never reach anyone else's, so treating it as one
	would switch the gate off almost everywhere it matters: `Employee` carries
	that tick on doctype after doctype and is held by nearly every member of
	staff, which is exactly the population a gated approver role is drawn from.
	It is honoured for what it does grant instead -- the gate withholds every
	row but the user's own -- rather than for access it does not confer.
	"""
	if doctype not in gated_doctypes():
		return None

	# Administrator short-circuits every permission check in core long before
	# a hook is consulted; saying so here keeps the two consistent rather than
	# implying this module could hold it back.
	if user in ("Administrator", "Guest"):
		return None

	applicable = applicable_perms(user, doctype)

	# No read access from any role. Core already denies this; claiming it as a
	# gate would only produce a misleading permission log.
	if not applicable:
		return None

	# Nothing ticked on any role this user actually holds.
	if not any(perm.get(GATE) for perm in applicable):
		return None

	ungated = [perm for perm in applicable if not perm.get(GATE)]
	if any(not perm.get(IF_OWNER) for perm in ungated):
		return None

	return OWN if ungated else NOTHING


def gate_applies(user: str, doctype: str) -> bool:
	"""Return True if the gate holds `user` back on `doctype` at all."""
	return gate_scope(user, doctype) is not None


def gate_satisfied(user: str, doctype: str) -> bool:
	"""Return True if `user` holds a User Permission aimed at `doctype` itself."""
	user_permissions = frappe.permissions.get_user_permissions(user)
	if not user_permissions:
		return False

	# `applicable_for` matched exactly, never core's
	# `filter_allowed_docs_for_doctype`, which also accepts a blanket permission
	# (`not applicable_for`) -- and blanket is the default. See the module docstring.
	return any(
		entry.get("applicable_for") == doctype
		for allow in constraining_doctypes(doctype)
		for entry in user_permissions.get(allow, [])
	)


def blocked_scope(user: str, doctype: str) -> str | None:
	"""What the gate withholds from `user` here, or `None` if it withholds nothing.

	The gate applying and the gate being satisfied are separate questions, and
	only the pair decides anything: a role can be gated and the user still hold
	the User Permission that opens it.
	"""
	scope = gate_scope(user, doctype)
	if scope is None or gate_satisfied(user, doctype):
		return None
	return scope


def constraining_doctypes(doctype: str) -> set[str]:
	"""Doctypes a User Permission could narrow `doctype` by.

	Its own name, plus the targets of every link field that has not opted out
	of user permissions -- the same fields core consults in
	`has_user_permission`.
	"""
	allowed = {
		field.options
		for field in frappe.get_meta(doctype).get_link_fields()
		if field.options and not field.get("ignore_user_permissions")
	}
	allowed.add(doctype)
	return allowed


# Hooks
# -----
# Registered against "*" so core consults them for every doctype. Both are
# deny-only by construction: core's `has_controller_permissions` documents that
# "controllers can only deny permission, they can not explicitly grant any
# permission that wasn't already present", and query conditions are ANDed into
# the where clause. Neither can widen access by mistake.


def permission_query_conditions(user: str, doctype: str | None = None, **kwargs) -> str:
	"""Narrow a list view to what the gate leaves: no rows, or the user's own."""
	if not doctype:
		return ""

	user = user or frappe.session.user
	scope = blocked_scope(user, doctype)
	if scope is None:
		return ""

	if scope == OWN:
		# The shape core builds for "Only if Creator" itself, in
		# `DatabaseQuery.build_match_conditions`, and ANDed alongside it.
		return f"`tab{doctype}`.`owner` = {frappe.db.escape(user, percent=False)}"

	return "1=0"


def has_permission(doc=None, ptype: str | None = None, user: str | None = None, **kwargs) -> bool:
	"""Deny a single document to a gated user who holds no User Permission.

	Core calls this only when it has a document in hand. Doctype-level checks
	("may this user open the list at all") go unhooked, which is why the query
	condition above matters: the list opens and is empty.
	"""
	if doc is None:
		return True

	user = user or frappe.session.user
	scope = blocked_scope(user, doc.doctype)
	if scope is None:
		return True

	# An ungated "Only if Creator" role still grants the user their own documents.
	return scope == OWN and doc.owner == user


# Query and Script Reports
# ------------------------
# Neither hook above runs here. `frappe.desk.query_report` checks the `report`
# right on the report's `ref_doctype` and then executes whatever the report
# author wrote -- HRMS' Salary Register, for one, selects `salary_slip.star`
# with no permission filtering at all. There is no generic way to narrow SQL
# nobody has seen, so a gated role is refused the report outright.
#
# Note this refuses gated roles even when their gate is satisfied: holding a
# User Permission makes a *list* safe, because core filters it, but it does
# nothing to a report that never consults one. Ungated roles are untouched, so
# an HR Manager still runs the Salary Register over everybody.


def _refuse_gated_report(report_name: str | None) -> None:
	if not report_name:
		return

	ref_doctype = frappe.get_cached_value("Report", report_name, "ref_doctype")
	if not ref_doctype or not gate_applies(frappe.session.user, ref_doctype):
		return

	frappe.throw(
		_(
			"Your access to {0} is restricted to specific records, and this report cannot honour "
			"that restriction. Use the {0} list instead."
		).format(_(ref_doctype)),
		frappe.PermissionError,
		title=_("Not permitted"),
	)


@frappe.whitelist()
def run_query_report(
	report_name: str,
	filters: str | dict | None = None,
	user: str | None = None,
	ignore_prepared_report: bool = False,
	custom_columns: str | list | None = None,
	is_tree: bool = False,
	parent_field: str | None = None,
	are_default_filters: bool = True,
	js_filters: str | list | None = None,
) -> dict:
	"""`frappe.desk.query_report.run`, refused for gated roles."""
	from frappe.desk.query_report import run

	_refuse_gated_report(report_name)

	return run(
		report_name=report_name,
		filters=filters,
		user=user,
		ignore_prepared_report=ignore_prepared_report,
		custom_columns=custom_columns,
		is_tree=is_tree,
		parent_field=parent_field,
		are_default_filters=are_default_filters,
		js_filters=js_filters,
	)


@frappe.whitelist()
def export_query_report() -> None:
	"""`frappe.desk.query_report.export_query`, refused for gated roles.

	Checked before delegating, so a background export is never enqueued for a
	user who may not have the rows.
	"""
	from frappe.desk.query_report import export_query

	_refuse_gated_report(frappe.form_dict.get("report_name"))

	return export_query()
