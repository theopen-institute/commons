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

None of this patches core. The marker is a `Permission Type` record, a core
extension point that creates a Check field on `DocPerm`, `Custom DocPerm` and
`DocShare` and draws it in the Role Permission Manager beside "Only if
Creator" -- see `safer_permissions.install.sync_permission_gates`. Enforcement
is core's two permission hooks, both of which accept a `"*"` key so they are
consulted for every doctype, and both of which can only ever deny:

	has_permission                 one document: read/write/submit/print/...
	permission_query_conditions    list view, report view, `frappe.get_list`

Query and Script Reports honour neither hook -- they run whatever SQL the
report author wrote, and no amount of hooking makes that respect User
Permissions -- so gated roles are refused them outright. See
`run_query_report`.

Which doctypes can be gated, and which User Permission each one demands, is
configured in `Permission Gate Settings`. Which roles are gated is configured
where role permissions already live, in the Role Permission Manager.
"""

import frappe
from frappe import _
from frappe.core.doctype.permission_type.permission_type import get_doctype_ptype_map
from frappe.permissions import get_allowed_docs_for_doctype
from frappe.utils import cint

# The custom permission type. One `Permission Type` record per gateable
# doctype registers it and gives it its checkbox; the Role Permission Manager
# labels the checkbox by title-casing this, so it reads "Require User
# Permission".
GATE = "require_user_permission"

SETTINGS = "Permission Gate Settings"

# Reaching a document at all. A role that grants neither is not granting
# access this module could usefully withhold.
READ_RIGHTS = ("read", "select")


def is_gateable(doctype: str) -> bool:
	"""Return True if `doctype` has the gate checkbox at all.

	`get_doctype_ptype_map` is site-cached and this is the first thing every
	hook below asks, so the overwhelmingly common answer -- an ordinary
	doctype nobody has gated -- costs one dict lookup.
	"""
	return GATE in get_doctype_ptype_map().get(doctype, [])


def gate_applies(user: str, doctype: str) -> bool:
	"""Return True if every role granting `user` read on `doctype` is gated.

	One ungated role is enough to see everything: an HR Manager who also holds
	`Employee` is an HR Manager. This mirrors how core resolves `if_owner`
	across roles in `get_role_permissions`, where an unrestricted grant beats a
	restricted one rather than intersecting with it.
	"""
	if not is_gateable(doctype):
		return False

	# Administrator short-circuits every permission check in core long before
	# a hook is consulted; saying so here keeps the two consistent rather than
	# implying this module could hold it back.
	if user in ("Administrator", "Guest"):
		return False

	roles = set(frappe.get_roles(user))
	applicable = [
		perm
		for perm in frappe.get_meta(doctype).permissions
		if perm.role in roles
		and cint(perm.permlevel) == 0
		and any(perm.get(right) for right in READ_RIGHTS)
	]

	# No read access from any role. Core already denies this; claiming it as a
	# gate would only produce a misleading permission log.
	if not applicable:
		return False

	return all(perm.get(GATE) for perm in applicable)


def gate_satisfied(user: str, doctype: str) -> bool:
	"""Return True if `user` holds the User Permissions the gate demands."""
	user_permissions = frappe.permissions.get_user_permissions(user)
	if not user_permissions:
		return False

	required = required_user_permissions(doctype)
	if required:
		# Every configured rule, not any of them: two rows for one doctype
		# means both restrictions have to be in place.
		return all(
			get_allowed_docs_for_doctype(user_permissions.get(allow, []), doctype) for allow in required
		)

	# No rule configured, yet a role is gated -- someone removed the rule row
	# and left the checkbox ticked. Fall back to the weaker question, "is this
	# user narrowed on this doctype at all", which is still closed by default.
	# `_configuration_gap` says so out loud rather than letting it pass.
	_configuration_gap(doctype)
	return any(
		get_allowed_docs_for_doctype(user_permissions.get(allow, []), doctype)
		for allow in constraining_doctypes(doctype)
	)


def is_blocked(user: str, doctype: str) -> bool:
	"""Return True if the gate applies to `user` here and is not satisfied."""
	return gate_applies(user, doctype) and not gate_satisfied(user, doctype)


def required_user_permissions(doctype: str) -> list[str]:
	"""The User Permission doctypes `Permission Gate Settings` demands here."""
	if not frappe.db.exists("DocType", SETTINGS):
		return []

	settings = frappe.get_cached_doc(SETTINGS)
	return [
		rule.required_user_permission
		for rule in settings.rules
		if rule.document_type == doctype and rule.required_user_permission
	]


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


def _configuration_gap(doctype: str) -> None:
	"""Record a gate with no rule behind it, on the file log and once only.

	Not `frappe.log_error`: this runs inside a permission check, on a path
	that answers every list query, and `Error Log` is a document -- inserting
	one would need its own permission checks, and would fail outright on the
	read-only connection reports run under. A row per query would be useless
	anyway, so each request says it at most once.
	"""
	reported = getattr(frappe.local, "tbs_permission_gaps", None)
	if reported is None:
		reported = frappe.local.tbs_permission_gaps = set()
	if doctype in reported:
		return
	reported.add(doctype)

	frappe.logger("permission_gate").warning(
		f"A role is gated on {doctype} but {SETTINGS} lists no rule for it, so the gate is "
		f"accepting any User Permission that narrows {doctype}. Add a rule naming the User "
		f"Permission this doctype should require."
	)


# Hooks
# -----
# Registered against "*" so core consults them for every doctype. Both are
# deny-only by construction: core's `has_controller_permissions` documents that
# "controllers can only deny permission, they can not explicitly grant any
# permission that wasn't already present", and query conditions are ANDed into
# the where clause. Neither can widen access by mistake.


def permission_query_conditions(user: str, doctype: str | None = None, **kwargs) -> str:
	"""Empty a list view rather than filter it: the gate allows no rows."""
	if doctype and is_blocked(user or frappe.session.user, doctype):
		return "1=0"
	return ""


def has_permission(doc=None, ptype: str | None = None, user: str | None = None, **kwargs) -> bool:
	"""Deny a single document to a gated user who holds no User Permission.

	Core calls this only when it has a document in hand. Doctype-level checks
	("may this user open the list at all") go unhooked, which is why the query
	condition above matters: the list opens and is empty.
	"""
	if doc is None:
		return True
	return not is_blocked(user or frappe.session.user, doc.doctype)


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
