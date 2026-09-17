"""Whitelisted endpoints for the self-service section of the TBS Commons frontend.

Two jobs, and the split between them is the point of the section. Somebody
*reads* a record they own and *proposes* corrections to it; the team responsible
reads the proposals and decides them. Nothing the owner does here writes to the
record, and nothing in this file does either -- the single write lives in
`RecordChangeRequest.on_submit`, in the approver's session, behind their own
permission check.

Every endpoint that touches a record takes the doctype as an argument and gets
its answers from that doctype's entry in `tbs_commons.self_service.policies`.
Employee is the first registered record and currently the only page, but nothing
below names it: adding a second record type is a registry entry and a page, not
a second copy of this module.

There is deliberately no endpoint here that returns the record itself. The page
reads it with the ordinary document API, filtered to the caller's own row, so
every permission the site has configured -- role permissions, User Permissions
and this app's gate in `tbs_commons.safer_permissions` -- applies to it without
this module restating any of them. What the server still owns is the *policy*:
`get_change_permissions` sends the field list, because most doctypes carry fields
that have no business on a self-service page even for their owner, and a frontend
choosing them for itself would start showing the next such field the day someone
adds one.

An earlier version of this file had a `get_my_record` that read the record with
`frappe.db.get_value`, and so answered to no permission at all. It was scoped --
it could only ever return the caller's own row, and only the policy's fields --
but it meant an administrator who gated the `Employee` role still had employees
reading their own record, which is not what they had configured. Resolving which
record is mine is not a reason to stop asking whether the answer may be shown.

Everything else is the proposal half, and it follows the same rule leave does:
what a request may set, which outcomes exist, which of them this user may apply
and how each one reads are the server's answers. A frontend that restated any of
them would be stating it where changing it does not change what the server does.

Outcomes come from the active Frappe Workflow where a site runs one -- states,
styling and transitions all the site's -- and otherwise off the `status` field's
own options. Neither path has a state name or a role name behind it here.
"""

import frappe

from tbs_commons import workflow as wf
from tbs_commons.self_service import registry

DOCTYPE = "Record Change Request"

# How many rows a queue returns. The badge counts to the same ceiling, so it
# never promises more than the page will show.
PAGE_LENGTH = 20

# What a request may set. Server-owned on purpose: `reference_name` is resolved
# from the session rather than accepted, `status` is the workflow's, and
# everything absent here -- the naming series, the posting date, the record
# title, the captured current values, the initial state -- is the doctype's to
# fill in.
REQUEST_FIELDS = ("changes", "reason", "request_type", "reference_name")

# What a `changes` row may carry. `current_value` is deliberately absent: it is
# captured from the referenced record by the controller, and a request that could
# state it could state a "before" that was never true.
CHANGE_ROW_FIELDS = ("fieldname", "proposed_value")

# What a queue row carries. Server-owned, so a field that turns out to need a
# permlevel or a rename is changed in one place.
LIST_FIELDS = [
	"name",
	# What the request asked for. Without it a queue cannot tell a deletion from
	# a correction, and a page cannot mark the record somebody wants removed.
	"request_type",
	"reference_doctype",
	"reference_name",
	"reference_title",
	"requested_by",
	"reason",
	"review_note",
	"reviewed_by",
	"status",
	"docstatus",
	"posting_date",
	"modified",
]

# How an outcome reads when no Workflow is styling it. The names are Frappe's own
# Workflow State styles, so a badge or a button is coloured from one vocabulary
# whether a workflow is running or not.
DEFAULT_DECISION_STYLES = {
	"Approved": "Success",
	"Rejected": "Danger",
	"Withdrawn": "Inverse",
	"Reversed": "Inverse",
}

# Which outcome is the affirmative one, and so the only one a page may apply
# without asking twice. Read off the style rather than the name, so a workflow
# that calls its approval something else still gets one solid button.
AFFIRMATIVE_STYLE = "Success"


def change_workflow():
	"""The active Workflow for `Record Change Request`, or None."""
	return wf.active_workflow(DOCTYPE)


def initial_state(workflow) -> str:
	"""The state an undecided request sits in.

	Derived rather than named: a workflow's first state is the one Frappe assigns
	a document that arrives without one, and without a workflow it is the `status`
	field's own default. Both queues and the badge are predicated on this, so a
	site that renames the state renames it once.
	"""
	if workflow and workflow.states:
		return workflow.states[0].state
	return frappe.get_meta(DOCTYPE).get_field("status").default or "Pending"


@frappe.whitelist()
def get_change_workflow() -> dict | None:
	"""The active Workflow definition, reduced to fields the SPA can render."""
	frappe.has_permission(DOCTYPE, "read", throw=True)
	return wf.describe(change_workflow())


def _may_review() -> bool:
	"""Whether this user has a review queue at all.

	The submit right, with or without a workflow -- which is where this
	deliberately differs from leave. There, a workflow may route an application
	back to its author without deciding it, so gating on submit would hide the
	page from people a site added those states for. Here approval *is* the
	submission by construction (see `RecordChangeRequest.on_submit`), so every
	transition that settles anything needs submit, and the two answers coincide.

	Gating on "holds a role some transition is open to" would be wrong here for a
	further reason: `Withdraw` is open to `Employee`, so every employee on the
	site would be told they have a review queue.
	"""
	return bool(frappe.has_permission(DOCTYPE, "submit"))


def _queue_filters(decided: bool, doctype: str | None = None) -> dict:
	"""Which requests are open, and which have been settled.

	`docstatus` alone will not do: an approved request is docstatus 1, but a
	rejected or withdrawn one stays at 0 -- that is what makes it amendable rather
	than dead. So the predicate is the state, and the state it compares against is
	derived (see `initial_state`) rather than spelled.
	"""
	state = initial_state(change_workflow())
	filters = {"status": state} if not decided else {"status": ["!=", state]}
	if doctype:
		filters["reference_doctype"] = doctype
	return filters


def _pending_count(doctype: str | None = None) -> int:
	"""The badge. Capped the way the queue is, so the two agree."""
	return len(
		frappe.get_list(
			DOCTYPE,
			filters=_queue_filters(decided=False, doctype=doctype),
			pluck="name",
			limit_page_length=PAGE_LENGTH,
		)
	)


def decision_vocabulary(workflow) -> list[dict]:
	"""Every outcome a reviewer could be offered, and how each one reads.

	With a workflow the outcomes are its actions and the styling is the site's: an
	action reads as the Workflow State it leads to. Without one they are the
	`status` field's options less the state a request starts in, styled by
	`DEFAULT_DECISION_STYLES`.

	`confirm` travels with the outcome rather than being inferred from its colour
	by whoever draws the button. Whether an irreversible choice deserves a second
	look is policy, and a site that adds an outcome should not have to know that a
	page somewhere decides that by reading a CSS variant.
	"""
	if workflow:
		styles = wf.state_styles(workflow)
		return [
			_decision(row["action"], styles.get(row["next_state"]))
			for row in wf.unique_actions(workflow.transitions)
		]

	field = frappe.get_meta(DOCTYPE).get_field("status")
	options = [option.strip() for option in (field.options or "").split("\n") if option.strip()]
	state = initial_state(None)
	return [_decision(option, DEFAULT_DECISION_STYLES.get(option)) for option in options if option != state]


def _decision(value: str, style: str | None) -> dict:
	return {
		"value": value,
		"style": style,
		"confirm": style != AFFIRMATIVE_STYLE,
	}


def status_display(row, workflow, styles: dict) -> tuple[str, str | None]:
	"""How a row reads to a person: its label, and the style to say it in.

	Settled here rather than in the page. With a workflow the state is the answer
	and the site's Workflow State supplies the style. Without one, `status` is
	still not quite the answer -- a cancelled request keeps the status it was
	approved with (see `RecordChangeRequest.on_cancel`, which deliberately leaves
	the field alone), so `docstatus` 2 has to be read first or a reversed change
	would go on reading as an approved one.
	"""
	if workflow:
		state = row.get(wf.state_field(workflow))
		return state or row.status, styles.get(state)
	if row.docstatus == 2:
		return frappe._("Reversed"), None
	return row.status, DEFAULT_DECISION_STYLES.get(row.status)


@frappe.whitelist()
def get_self_service_nav() -> list[dict]:
	"""Every self-service page this user could open, in sidebar order.

	The navigation is configuration now, so the sidebar reads it rather than
	naming pages. `can_read` is permission on the record doctype, and the rows
	are not filtered by it: a page that vanishes leaves someone unable to tell a
	missing feature from a missing permission, and the page itself explains which
	it is. What *is* filtered is anything this user could never open -- nothing,
	currently, since every enabled record is offered and the page does the rest.

	Deliberately cheap. It runs on every page load, so it answers from the cached
	registry plus one permission check per record, and asks nothing about whether
	the user actually owns anything.
	"""
	rows = []
	for doctype in registry.registered():
		current = registry.policy(doctype)
		rows.append(
			{
				"doctype": doctype,
				"label": current["label"],
				"slug": current["slug"],
				"icon": current["icon"],
				"singular": current["singular"],
				"can_read": bool(frappe.has_permission(doctype, "read")),
			}
		)
	return rows


@frappe.whitelist()
def get_change_permissions(doctype: str | None = None) -> dict:
	"""What the session user may do in this section, plus any review backlog.

	`read` and `has_record` are deliberately two answers rather than one, because
	they drive two different things and conflating them hides the section from
	the people it exists to help.

	`read` is whether this user may use the section at all -- a permission, the
	way `leaveCan.read` is -- and so whether the navigation should offer it. It is
	not conditioned on owning a record: a login with no employee record behind it
	still needs to be told that, and a section that simply vanishes leaves them
	unable to tell a missing feature from a missing permission. It also has to
	stay true for a reviewer who is not themselves an employee, or the review
	queue goes with it.

	`has_record` is whether they actually own one, which is the page's question:
	it decides between the profile and the "your login isn't linked" notice, and
	it gates the button that raises a request. Asked only when a `doctype` is
	named -- the review queue spans every registered doctype and needs no such
	answer.

	`proposable` is the field allowlist for that doctype, sent so the form offers
	exactly what the save would accept. `decisions` is here so a reviewer's
	buttons are the outcomes the server will actually take, styled as the site
	styles them.
	"""
	workflow = change_workflow()
	can_review = _may_review()
	# `session_records`, not `session_record`: a policy may be one-per-owner
	# (an employee record) or many (their bank accounts), and this endpoint
	# answers for both. "Do they have any" is the question either way.
	owns = bool(doctype) and bool(registry.session_records(doctype, limit=1))

	return {
		"doctype": doctype,
		"registered": registry.registered(),
		"read": bool(frappe.has_permission(DOCTYPE, "read")),
		# Read permission on the *record* doctype, which `read` above is not --
		# that one is about change requests. A page that fetches the records
		# through the document API has to know, or it fires a call the framework
		# answers with a bare 403 where an explanation belongs.
		"can_read_records": bool(frappe.has_permission(doctype, "read")) if doctype else False,
		"has_record": owns,
		# Why there is no record to show, when there is not one. Three answers,
		# because "you have no record" and "you may not see your record" send the
		# reader to different people -- HR for the first, whoever administers
		# permissions for the second -- and a page that cannot tell them apart has
		# to guess, which is how it ends up telling an employee their record does
		# not exist while they are looking at their own payslip.
		"record_access": _record_access(doctype) if doctype else "missing",
		# `proposable` as well as `create`: a record type this section only reads
		# has no fields to propose, and a page told it may request against one
		# would draw a control that can produce nothing the server would accept.
		"request": (
			owns
			and bool(registry.proposable_fields(doctype) if doctype else [])
			and bool(frappe.has_permission(DOCTYPE, "create"))
		),
		"review": can_review,
		"pending_reviews": _pending_count() if can_review else 0,
		"proposable": registry.proposable_fields(doctype) if doctype else [],
		# The page's whole field layout: sections in order, each field with the
		# label, control, options and mandatory flag read from the doctype's own
		# meta. Sent rather than held in the frontend so adding a field to a
		# profile is a desk edit, and so a label can never drift from the one the
		# desk shows.
		"sections": registry.field_definitions(doctype) if doctype else [],
		# What the page may show, so the field list stays the server's while the
		# record itself is fetched through the permission-enforcing document API.
		"display": registry.display_fields(doctype) if doctype else [],
		# The filter that finds the caller's own row. Sent rather than assembled
		# in the page, so `owner_field` is named once -- here -- and a policy that
		# resolves ownership differently needs no matching edit there.
		"owner_field": registry.policy(doctype)["owner_field"] if doctype else None,
		# What that field should equal: the login for a policy that names its
		# owner directly, the owning record's name for one that chains. Resolved
		# here so a page filtering through the document API asks the same
		# question the server would, without knowing which shape it is.
		"owner_value": registry.owner_value(doctype) if doctype else None,
		"record_filters": (registry.policy(doctype).get("filters") or {}) if doctype else {},
		# Whether one record is expected or several. The page renders a profile
		# for the first and a list for the second.
		"singular": bool(registry.policy(doctype).get("singular")) if doctype else False,
		# Whether an owner may ask for a record of this type to be created or
		# removed. Both off unless the configuration turns them on, and both
		# meaningless for a record type with one record per owner.
		"allow_new": bool(registry.policy(doctype).get("allow_new")) if doctype else False,
		"allow_delete": bool(registry.policy(doctype).get("allow_delete")) if doctype else False,
		# How this record type introduces and excuses itself. Configuration, so a
		# site can say "talk to payroll" where a generic line would send somebody
		# to the wrong place -- see `Self Service Record`.
		"label": registry.policy(doctype)["label"] if doctype else None,
		"slug": registry.policy(doctype)["slug"] if doctype else None,
		"read_only_notice": registry.policy(doctype)["read_only_notice"] if doctype else None,
		"empty_notice": registry.policy(doctype)["empty_notice"] if doctype else None,
		"decisions": decision_vocabulary(workflow),
		"page_length": PAGE_LENGTH,
	}


def _record_access(doctype: str) -> str:
	"""Whether this user's record is `visible`, `forbidden`, or `missing`.

	`visible` and `missing` are the ordinary answers. `forbidden` is the one worth
	having: a row exists that the policy claims for this user, and the site is not
	letting them read it -- a permissions question, not an HR one.

	The existence test is a raw count of the caller's own row and discloses
	nothing but its existence; see `registry.record_exists`.
	"""
	if registry.session_records(doctype, limit=1):
		return "visible"
	# Existence is the discriminator, not permission -- which is why the raw
	# check exists. Lacking read and having no rows are indistinguishable from
	# where the reader sits, and "there are none" is the more useful of the two:
	# for `Employee` the missing role *is* the missing record, so telling a
	# non-employee they lack access would send them to the wrong person. The
	# moment a row does appear, this flips to `forbidden` and names the right one.
	return "forbidden" if registry.record_exists(doctype) else "missing"


def _decorate(requests: list, workflow) -> list:
	"""Give each row its label, its style, its diff and the outcomes this user may apply."""
	styles = wf.state_styles(workflow)
	names = [row.name for row in requests]
	moves = wf.permitted_transitions(DOCTYPE, names, workflow) if workflow else {}
	can_submit = _may_review()
	state = initial_state(workflow)

	for request in requests:
		if workflow:
			request.actions = [action["action"] for action in moves.get(request.name) or []]
		else:
			# No workflow: any outcome, but only on a request still awaiting one
			# and only for someone who could submit it.
			offered = [row["value"] for row in decision_vocabulary(None)]
			request.actions = offered if can_submit and request.status == state else []
		request.can_decide = bool(request.actions)
		# Whether this request is still awaiting a decision. Server-owned because
		# `docstatus` cannot answer it -- a rejected or withdrawn request stays at
		# 0 -- and because the state it compares against is derived rather than
		# spelled. The read-only page reads it to mark a field that already has a
		# proposal against it, so nobody raises the same correction twice.
		request.open = request.get(wf.state_field(workflow)) == state
		request.status_label, request.status_style = status_display(request, workflow, styles)
		request.changes = get_change_rows(request.name)
	return requests


def get_change_rows(parent: str) -> list[dict]:
	"""The proposed field changes on one request, in the order they were entered.

	A child table, so `get_list` on the parent cannot bring it back -- and a queue
	is unreadable without it: the whole content of a request is its diff.
	`parent_doctype` is what makes this inherit the parent's permissions rather
	than needing rows of its own.
	"""
	return frappe.get_all(
		"Record Change Item",
		filters={"parent": parent, "parenttype": DOCTYPE},
		fields=["fieldname", "label", "current_value", "proposed_value"],
		order_by="idx asc",
		parent_doctype=DOCTYPE,
	)


def _with_state_field(workflow) -> list[str]:
	state_field = wf.state_field(workflow)
	return LIST_FIELDS if state_field in LIST_FIELDS else [*LIST_FIELDS, state_field]


@frappe.whitelist()
def get_my_changes(doctype: str | None = None) -> list[dict]:
	"""The session user's own requests, newest first.

	Two ways a request is theirs, and both are needed.

	It is *about* a record they own -- which is what makes one HR raised on their
	behalf theirs to follow. Ownership is resolved per record type rather than
	assumed singular: an owner with three bank accounts has three, and an earlier
	version of this resolved only one, so a page listing several showed no
	history at all.

	Or they *raised* it -- the only way a `New` request can be theirs, because it
	names no record until it is approved. Without this a creation request was
	invisible to the person who made it until somebody approved it.

	A user with neither has none: an empty list, not everybody else's, which is
	what an unfiltered read would hand a reviewer.
	"""
	# `get_list` throws for a user with no read on the request doctype, and one of
	# the callers is a page working out whether it has anything to show. "You have
	# none" is the same answer as far as it is concerned.
	if not frappe.has_permission(DOCTYPE, "read"):
		return []
	owned = _my_records(doctype)
	user = frappe.session.user
	workflow = change_workflow()
	filters = {"reference_doctype": doctype} if doctype else {}
	requests = frappe.get_list(
		DOCTYPE,
		filters=filters,
		or_filters=[
			# `or_filters` with an empty `in` list matches nothing, which is the
			# wrong answer for a user who owns no records but has raised requests.
			["reference_name", "in", sorted({name for _d, name in owned}) or [""]],
			["requested_by", "=", user],
		],
		fields=_with_state_field(workflow),
		order_by="creation desc",
		limit_page_length=PAGE_LENGTH,
	)
	# `reference_name` alone could collide across doctypes, so the pair is what
	# decides -- filtered here rather than in SQL because the set is a handful of
	# records, not a table. A request this user raised is theirs whatever it
	# points at, including nothing yet.
	return _decorate(
		[
			row
			for row in requests
			if row.requested_by == user or (row.reference_doctype, row.reference_name) in owned
		],
		workflow,
	)


def _my_records(doctype: str | None) -> set[tuple[str, str]]:
	"""Every registered record this session owns, as (doctype, name).

	Both shapes: one record per owner, or several. `session_records` answers for
	either, and goes through `get_list`, so a record the site withholds is not
	counted as theirs here.
	"""
	owned: set[tuple[str, str]] = set()
	for name in [doctype] if doctype else registry.registered():
		for row in registry.session_records(name, ["name"]):
			owned.add((name, row.name))
	return owned


@frappe.whitelist()
def get_change_queue(decided: int = 0, doctype: str | None = None) -> list[dict]:
	"""Requests waiting on a decision, or ones already settled.

	Here rather than in a list query the frontend builds, so "waiting" means one
	thing: the page's rows, the badge counting them and the endpoint that writes
	the decision all read `_queue_filters`, and none of them can drift into a
	slightly different idea of what is open.

	Every reviewer sees every open request rather than only ones that name them.
	Unlike leave, a correction has no named approver on it -- there is nothing on
	an employee record that says who checks their address -- so the queue belongs
	to the responsible team, and `get_list` is what settles which of it this user
	may read.
	"""
	decided = bool(frappe.utils.cint(decided))
	frappe.has_permission(DOCTYPE, "read", throw=True)
	workflow = change_workflow()

	requests = frappe.get_list(
		DOCTYPE,
		filters=_queue_filters(decided, doctype),
		fields=_with_state_field(workflow),
		# Oldest first while they are still decisions to make -- somebody has been
		# waiting longest; most recently touched first once they are history.
		order_by="modified desc" if decided else "creation asc",
		limit_page_length=PAGE_LENGTH,
	)
	requests = _decorate(requests, workflow)
	# A request nobody can act on is not waiting on this user. Only meaningful
	# with a workflow, where a transition's own condition may rule them out.
	if not decided and workflow:
		requests = [row for row in requests if row.actions]
	return requests


@frappe.whitelist(methods=["POST"])
def request_change(doctype: str, doc: str | dict) -> dict:
	"""Raise a change request against the `doctype` record behind this session.

	Three shapes share this door. A `Change` names a record and carries the
	values to correct; a `New` names none and carries the values to start it
	with; a `Delete` names one and carries nothing. Which of them a record type
	allows is configuration -- the controller refuses the rest -- and which
	record a request may be about is settled here by ownership rather than by
	what the caller sent.

	Through here rather than straight at the document API so the fields a request
	may set are the server's. Everything `REQUEST_FIELDS` leaves out -- the naming
	series, the posting date, the record title, the captured current values, the
	resolved owner, the workflow's initial state -- is filled in by the doctype,
	so a site that customises any of them gets what it configured.

	Which fieldnames the rows may name is not checked here either. That is
	`RecordChangeRequest.validate_rows`, which runs on every save from any route,
	including the desk -- a check in this function would only cover the one door
	it guards.
	"""
	values = frappe.parse_json(doc) or {}
	if not isinstance(values, dict):
		frappe.throw(frappe._("A Record Change Request document is required."))
	if values.get("doctype") not in (None, DOCTYPE):
		frappe.throw(frappe._("Only change requests can be created here."))

	# Refuses an unregistered doctype before anything is resolved against it.
	registry.policy(doctype)

	request = {field: values[field] for field in REQUEST_FIELDS if field in values}
	request["doctype"] = DOCTYPE
	request["reference_doctype"] = doctype
	request.setdefault("request_type", "Change")

	if request["request_type"] == "New":
		# Nothing to name yet. The owner is resolved by the controller from this
		# session, so a creation request cannot be raised on somebody else's behalf
		# by naming them here.
		request.pop("reference_name", None)
	else:
		named = request.get("reference_name")
		if not named:
			# A singular record type has one answer, so the page need not send it.
			# Anything else has to say which record it means.
			owned = registry.session_records(doctype, ["name"], limit=1)
			if not owned:
				frappe.throw(
					frappe._("You have no {0} record for this request.").format(frappe._(doctype)),
					frappe.ValidationError,
				)
			named = owned[0].name
			request["reference_name"] = named
		if not registry.session_owns(doctype, named):
			frappe.throw(
				frappe._("You can only raise requests about your own records here."),
				frappe.PermissionError,
			)
	# Rows reduced to what a request may state. `current_value` is the
	# controller's to capture, and `label` the meta's to supply.
	request["changes"] = [
		{field: row[field] for field in CHANGE_ROW_FIELDS if field in row}
		for row in (values.get("changes") or [])
		if isinstance(row, dict)
	]
	return frappe.get_doc(request).insert().as_dict()


@frappe.whitelist(methods=["POST"])
def decide_change(name: str, decision: str, note: str | None = None) -> dict:
	"""Settle a request, by the route the site has configured.

	With a Workflow that is `apply_workflow`, so the transition's own conditions,
	permitted roles and next state decide what happens and what is written.
	Without one, the outcome is written to `status` and -- when it is the one that
	carries the request to docstatus 1 -- submitted, which is what applies the
	change to the referenced record.

	The note is written before the decision rather than after, so a rejection and
	its reason land in the same transaction. A note saved separately is a note
	that can go missing while the refusal stands, which is the one combination the
	requester cannot make sense of.
	"""
	workflow = change_workflow()
	offered = [option["value"] for option in decision_vocabulary(workflow)]
	if decision not in offered:
		frappe.throw(
			frappe._("Decision must be one of {0}").format(", ".join(offered)),
			frappe.ValidationError,
		)

	doc = frappe.get_doc(DOCTYPE, name)

	if note is not None:
		# permlevel 1: a user without write access there has the change silently
		# reverted rather than refused, so it is checked rather than assumed.
		doc.check_permission("write")
		doc.review_note = note
		doc.reviewed_by = frappe.session.user

	if workflow:
		# No submit check here: `apply_workflow` already refuses an action this
		# user's roles or the transition's own condition do not allow, having
		# read-checked the document through `get_transitions` on the way.
		from frappe.model.workflow import apply_workflow

		if note is not None:
			doc.save()
		doc = apply_workflow(doc, decision)
		return {
			"name": doc.name,
			"status": doc.get(wf.state_field(workflow)),
			"docstatus": doc.docstatus,
		}

	doc.check_permission("submit")
	if doc.status != initial_state(None):
		frappe.throw(
			frappe._("{0} has already been settled as {1}.").format(name, doc.status),
			frappe.ValidationError,
		)

	doc.status = decision
	doc.save()

	# Approval is the submission -- it is what applies the change to the record.
	# Which outcome that is comes from the styling, not from its name, so a site
	# that renamed it still submits.
	affirmative = {
		option["value"] for option in decision_vocabulary(None) if option["style"] == AFFIRMATIVE_STYLE
	}
	if decision in affirmative:
		doc.submit()

	return {"name": doc.name, "status": doc.status, "docstatus": doc.docstatus}
