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

None of this patches core. The marker is one Check field on `DocPerm` and
`Custom DocPerm`, which the Role Permission Manager draws beside "Only if
Creator" -- declared in `commons/fixtures/custom_field.json`. Enforcement
is core's two permission hooks, both of which accept a `"*"` key so they are
consulted for every doctype, and both of which can only ever deny:

	has_permission                 one document: read/write/submit/print/...
	permission_query_conditions    list view, report view, `frappe.get_list`

Query and Script Reports honour neither hook -- they run whatever SQL the
report author wrote, and no amount of hooking makes that respect User
Permissions -- so gated roles are refused them outright. See
`run_query_report`.

Sharing is out of scope, deliberately. Core re-grants around both hooks for a
shared document -- `has_permission` falls through to `false_if_not_shared` after
a controller has denied, and `DatabaseQuery` ORs the shared names in outside the
query condition -- so a gated user still reaches a document somebody shared with
them. That is what sharing is for. The gate is about access nobody decided to
give.

Configured in one place: the Role Permission Manager, beside "Only if Creator".
Opt-in, site-wide: nothing here enforces anything until "Enable Require User
Permission Gate" is ticked in Commons Settings, and unticking it stands the gate
down with the ticks intact -- the first thing to try when permissions misbehave
after an upgrade. See `gate_scope`.

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

from typing import Any

import frappe

# `import frappe` alone does not bind the submodule, and `gate_satisfied` calls
# `frappe.permissions.get_user_permissions`. On a site something else has always
# imported it first, so the omission never showed; imported here so the gate does
# not depend on that.
import frappe.permissions
from frappe import _
from frappe.utils import cint

from commons.commons_core import settings

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

# Where a report's results are left lying about once it has run. See below.
PREPARED_REPORT = "Prepared Report"


def applicable_perms(user: str, doctype: str) -> list:
	"""The rows that grant `user` a read right over whole documents of `doctype`.

	Read from the meta, which is where core reads them: once a doctype has been
	customised its `Custom DocPerm` rows replace its `DocPerm` rows entirely, and
	`frappe.get_meta` has already resolved which of the two apply. It has also
	already been loaded -- core builds the meta before it consults either hook
	below -- so this costs a cached lookup and no query.

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
	# Administrator short-circuits every permission check in core long before
	# a hook is consulted; saying so here keeps the two consistent rather than
	# implying this module could hold it back.
	if user in ("Administrator", "Guest"):
		return None

	# Not switched on in Commons Settings. Everything the gate enforces asks here
	# first -- the list condition, the document check, the report refusals and
	# self-service -- so this one answer stands the whole module down, and the
	# ticks stay where they are for when it is switched on.
	if not gate_switched_on():
		return None

	# Nothing ticked on any role this user holds -- which is the answer for every
	# doctype nobody has gated, and so the answer almost every time this is asked.
	# A user with no read access at all lands here too: core already denies that,
	# and claiming it as a gate would only produce a misleading permission log.
	applicable = applicable_perms(user, doctype)
	if not any(perm.get(GATE) for perm in applicable):
		return None

	ungated = [perm for perm in applicable if not perm.get(GATE)]
	if any(not perm.get(IF_OWNER) for perm in ungated):
		return None

	return OWN if ungated else NOTHING


def gate_switched_on() -> bool:
	"""Return True if a System Manager has switched the gate on for this site."""
	return settings.feature_enabled(settings.ENABLE_PERMISSION_GATE)


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
		for allow in user_permissions.keys() & constraining_doctypes(doctype)
		for entry in user_permissions[allow]
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
	# Compared the way core compares it in `get_doc_permissions`, and the way the
	# database compares the condition above: without regard to case. An exact
	# compare here would list a row and then refuse to open it.
	return scope == OWN and (doc.owner or "").lower() == user.lower()


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
#
# Running a report is not the only way to its rows. A `Prepared Report` is the
# result of one, generated in the background and left in a file, and core reaches
# it without going near `query_report.run`: `make_prepared_report` enqueues the
# job after nothing but the doctype-level checks, and `download_attachment` and
# `enqueue_json_to_csv_conversion` then serve the file to anyone core's own rule
# lets read the record -- which is anyone who may access the report. So both ends
# are refused: making one, and reading one that already exists.
#
# Standing in front of core
# -------------------------
# The three wrappers are `override_whitelisted_methods` entries, and that is the
# one part of this module no switch can take out: hooks are read before any
# setting is, so the wrappers answer at core's addresses whether the gate is on
# or not. What can be done is to make them as thin as possible, so that the
# ways an upgrade could break them each end somewhere sensible:
#
#   core adds, drops or renames an argument
#       Nothing is copied. Each wrapper takes the report's name and `**kwargs`
#       and forwards through `frappe.call`, which hands core exactly the
#       arguments core's own signature names today -- the same filtering the
#       request handler would have done. Core's decorators (`run` is
#       `@frappe.read_only()`) still apply, because it is core's function that
#       runs.
#   core moves or deletes one of the functions
#       Looked up by its dotted path when a report is asked for, never imported
#       at module load, so the rest of the app -- and every permission check --
#       keeps working. The request that needed it gets a message that says
#       what happened, and the Error Log gets the traceback.
#   the gate's own check fails
#       Refused, not waved through: this is a permission check, and failing open
#       would hand a gated role the rows it exists to withhold. The message says
#       how to get reports back -- untick the gate, and the check is never made.
#   core stops calling one of these paths
#       Then the override is silently bypassed and a gated role gets the report.
#       Nothing at run time can see that happen, so `test_permission_gate`'s
#       `CoreStillLooksTheSame` checks it against the installed Frappe -- run it
#       after every upgrade.
#
# All three are a bare `@frappe.whitelist()`, so all three answer a GET -- and
# `make_prepared_report` inserts a document on one, which is the shape
# `commons_core.cache` shuts with `methods=["POST"]` for exactly this reason.
# That is inherited rather than chosen: standing in for core at core's own
# address, they have to accept what core accepts, and a narrower `methods` here
# would refuse desk traffic that core sends as a GET. Said out loud so the next
# reader does not take it for this app's decision about CSRF.

# Core's own addresses, which are also the keys in `hooks.override_whitelisted_methods`.
CORE_RUN = "frappe.desk.query_report.run"
CORE_EXPORT = "frappe.desk.query_report.export_query"
CORE_MAKE_PREPARED = "frappe.core.doctype.prepared_report.prepared_report.make_prepared_report"


def gated_report_doctype(report_name: str | None, user: str | None = None) -> str | None:
	"""The doctype `report_name` reports on, if the gate holds `user` back there.

	`None` when there is nothing to refuse: no report, a report naming no doctype,
	or a user no gate applies to. The session is read only once there is something
	to read it for, so deciding about no report at all needs no session.
	"""
	# The switch first, so a site that has the gate off never reaches a line
	# below -- which is what makes unticking it the way out if one of them breaks.
	if not report_name or not gate_switched_on():
		return None

	ref_doctype = frappe.get_cached_value("Report", report_name, "ref_doctype")
	if not ref_doctype or not gate_applies(user or frappe.session.user, ref_doctype):
		return None

	return ref_doctype


def has_prepared_report_permission(
	doc=None, ptype: str | None = None, user: str | None = None, **kwargs
) -> bool:
	"""Deny a gated user a report's stored results.

	Registered for `Prepared Report` alongside the `"*"` hook above rather than
	folded into it: core composes every hook for a doctype with every hook for
	`"*"` and denies if any of them does, so this is simply one more voice. The
	gate is asked about the doctype the report reads, never about `Prepared
	Report` itself, which nobody ticks.
	"""
	if doc is None:
		return True

	return gated_report_doctype(doc.report_name, user) is None


def _core(path: str):
	"""Core's own function at `path`, or a refusal that says why there is none."""
	try:
		return frappe.get_attr(path)
	except Exception:
		frappe.log_error(
			title=f"Commons: {path} not found",
			message=(
				f"Commons forwards this endpoint to Frappe's {path}, and this version of Frappe "
				"does not have it. Every report request that reaches it will fail until "
				"`override_whitelisted_methods` in commons/hooks.py is updated.\n\n"
			)
			+ frappe.get_traceback(),
		)
		frappe.throw(
			_(
				"This report could not be run: this version of Frappe has changed in a way Commons "
				"has not been updated for. Details are in the Error Log."
			),
			title=_("Report unavailable"),
		)


def _refuse_gated_report(report_name: str | None) -> None:
	try:
		ref_doctype = gated_report_doctype(report_name)
	except Exception:
		# Fail closed. See "Standing in front of core" above.
		frappe.log_error(title="Commons: permission gate check failed", message=frappe.get_traceback())
		frappe.throw(
			_(
				"This report was not run because Commons could not check whether your access to it "
				"is restricted. Details are in the Error Log. Unticking Enable Require User Permission "
				"Gate in Commons Settings runs reports exactly as Frappe would."
			),
			frappe.PermissionError,
			title=_("Not permitted"),
		)

	if not ref_doctype:
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
def run_query_report(report_name: str | None = None, **kwargs: Any) -> dict:
	"""`frappe.desk.query_report.run`, refused for gated roles.

	`report_name` is optional here although core requires it, so that a request
	without one reaches core and gets core's own error rather than a Python one
	about this wrapper's signature.
	"""
	_refuse_gated_report(report_name)
	return frappe.call(_core(CORE_RUN), report_name=report_name, **kwargs)


@frappe.whitelist()
def make_prepared_report(report_name: str | None = None, **kwargs: Any) -> dict:
	"""`frappe.core.doctype.prepared_report.prepared_report.make_prepared_report`, refused for gated roles.

	Checked before delegating, so the background job is never enqueued -- core
	inserts the record with `ignore_permissions=True`, and nothing downstream of
	that asks again.
	"""
	_refuse_gated_report(report_name)
	return frappe.call(_core(CORE_MAKE_PREPARED), report_name=report_name, **kwargs)


@frappe.whitelist()
def export_query_report(**kwargs: Any) -> None:
	"""`frappe.desk.query_report.export_query`, refused for gated roles.

	Checked before delegating, so a background export is never enqueued for a
	user who may not have the rows. Core reads its arguments from `form_dict`
	rather than its signature, so the report's name is read from there too.
	"""
	_refuse_gated_report(frappe.form_dict.get("report_name"))
	return frappe.call(_core(CORE_EXPORT), **kwargs)
