"""A proposal to correct a record somebody owns, and the decision on it.

Most records are maintained by the team responsible for them. That is the right
default -- a record half the organisation can edit is a record nobody can rely
on -- but it makes the person who actually knows their own phone number the one
person who cannot fix it, and the fix then travels by email and gets forgotten.
This doctype is the missing third option: the owner says what is wrong, the
responsible team agrees or does not, and the record only ever changes through a
decision somebody made on purpose.

It is deliberately not about employees. A request names a doctype and a document,
and everything that gives that pair meaning -- whose record it is, which of its
fields may be proposed, how it reads in a queue -- comes from that doctype's
`Self Service Record`, through `commons.self_service.registry`. The app
registers none: a site says which record types are self-service, and a second
one is a configuration document and a page, not another copy of this file.

So the self-service half is read-only by construction. Nothing here writes to the
referenced record until `on_submit`, and `on_submit` runs under whoever approved
it, with `check_permission("write")` on that record -- so the write is the
responsible team's write, made in their session, and an approver without the
right to make it is refused rather than quietly granted it by proxy.

Approval is the submission, as it is for `Procurement Request`: every state
before a decision is docstatus 0, `Rejected` and `Withdrawn` included, and only
`Approved` reaches docstatus 1. That is what lets the apply hang off `on_submit`
rather than off the name of a state, so a site that renames its workflow states
keeps working.

The `current_value` on each row is captured, never typed, and re-captured on
every validate. Validate runs inside `submit()`, so the value an approved request
records is the value the record held immediately before the change -- an accurate
before-and-after rather than whatever the field said when the request was first
raised.
"""

import re
from typing import ClassVar

import frappe
from frappe import _
from frappe.model.document import Document

from commons.self_service import registry

# The state a request starts in, and the only one a decision moves it out of.
# Also the value `on_submit` overwrites when a site runs no Workflow at all, so
# an approved request never reads as still pending.
PENDING = "Pending"
APPROVED = "Approved"


def normalized(value) -> str | None:
	"""A field value reduced to the two states Frappe actually stores.

	Frappe writes an empty field as `''` from a form and `None` from Python, and
	compares neither to the other. Every comparison in this file goes through
	here, so "cleared it" and "left it blank" are one answer rather than a
	spurious change that gets written on approval.
	"""
	if value is None:
		return None
	text = str(value).strip()
	return text or None


def name_field_of(doctype: str) -> str | None:
	"""The field whose value becomes a document's name, where there is one.

	Narrower than it looks, and the reason a popup is not always offered. A
	free-form value has to come back as the *name* of the created document,
	because that is what the Link on the referenced record gets set to. Only
	`field:` naming and user-set naming do that: a doctype named by series or by
	hash would take the value as a title and answer to a name nobody proposed, so
	the link would still resolve to nothing and the approval would still refuse.
	"""
	meta = frappe.get_meta(doctype)
	autoname = (meta.autoname or "").strip()
	if autoname.startswith("field:"):
		return autoname.split(":", 1)[1].strip() or None
	if autoname.lower() == "prompt" or meta.naming_rule == "Set by user":
		return "name"
	return None


def near_matches(doctype: str, value: str, limit: int = 3) -> list[str]:
	"""Records already on file whose name resembles the one being proposed.

	Against duplicates rather than for convenience. A free-form value is typed,
	so `Standard Chartered` arriving at a site that already holds `Standard
	Chartered Bank` is one master record too many -- and the approver is the only
	person placed to notice before it exists. Matched on the longest word in the
	value: a `like` on the whole string finds nothing, since not matching is the
	reason we are here.

	Through `get_list`, so somebody who may not read the target doctype is not
	shown its contents by way of a suggestion.
	"""
	if not frappe.has_permission(doctype, "read"):
		return []
	words = sorted((word for word in re.split(r"\W+", value) if len(word) >= 4), key=len, reverse=True)
	if not words:
		return []
	return frappe.get_list(
		doctype,
		filters={"name": ["like", f"%{words[0]}%"]},
		pluck="name",
		limit_page_length=limit,
		order_by="modified desc",
	)


class RecordChangeRequest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from commons.self_service.doctype.record_change_item.record_change_item import (
			RecordChangeItem,
		)

		amended_from: DF.Link | None
		changes: DF.Table[RecordChangeItem]
		naming_series: DF.Literal["CHG-.YYYY.-"]
		posting_date: DF.Date
		reason: DF.SmallText | None
		reference_doctype: DF.Link
		reference_name: DF.DynamicLink
		reference_title: DF.Data | None
		requested_by: DF.Link
		review_note: DF.SmallText | None
		reviewed_by: DF.Link | None
		status: DF.Data
	# end: auto-generated types

	# What a request can ask for. `Change` corrects a record that exists, `New`
	# asks for one to be created, `Delete` asks for one to be removed. They share
	# everything that matters -- the same field allowlist, the same reviewers and
	# the same workflow -- and differ only in what exists at each end.
	CHANGE = "Change"
	NEW = "New"
	DELETE = "Delete"

	# Which configuration switch each mode answers to. `Change` has none: a record
	# type with proposable fields is already saying its owners may correct them.
	MODE_SWITCH: ClassVar[dict[str, str]] = {NEW: "allow_new", DELETE: "allow_delete"}

	@property
	def is_new_record(self) -> bool:
		return self.request_type == self.NEW

	@property
	def is_deletion(self) -> bool:
		return self.request_type == self.DELETE

	def onload(self) -> None:
		"""What the desk form needs to know and cannot work out for itself.

		A free-form value naming a document that does not exist is the one thing
		an approver cannot see on this form: the row says `Standard Chartered`,
		and whether there is a `Bank` by that name is a question about a different
		doctype. Sent with the document rather than fetched by the form, so the
		notice is there on the first paint and costs no extra round trip.

		Answered here rather than only at `check_links_exist`, which is the guard
		and stays the guard. The difference is when: this reaches the approver
		while they are reading the request, instead of as the refusal that follows
		their decision.

		Failing softly on purpose. A form that cannot be opened is a worse answer
		to an unregistered record type than a form without a notice on it -- and
		the approval itself still refuses, with the reason.
		"""
		try:
			self.set_onload("missing_links", self.missing_links())
		except frappe.PermissionError:
			self.set_onload("missing_links", [])

	def validate(self) -> None:
		# Refuses an unregistered doctype outright, and does it before anything
		# else reads a policy that does not exist.
		policy = registry.policy(self.reference_doctype)
		self.validate_mode_allowed(policy)
		if self.docstatus == 0:
			self.validate_raiser()
		self.set_reference_title()
		self.validate_rows()
		self.capture_current_values()
		self.validate_something_proposed()

	def validate_mode_allowed(self, policy: dict) -> None:
		"""Creating and deleting are off unless the configuration turns them on.

		Correcting is not, because a record type with proposable fields is already
		saying its owners may correct them. Creating a record and destroying one
		are different powers, and a site should grant each on purpose -- see
		`Self Service Record`.
		"""
		switch = self.MODE_SWITCH.get(self.request_type)
		if switch and not policy.get(switch):
			frappe.throw(
				_("{0} records cannot be {1} through a request here.").format(
					_(self.reference_doctype),
					_("created") if self.is_new_record else _("deleted"),
				),
				frappe.PermissionError,
			)

	def set_reference_title(self) -> None:
		"""How the request reads in a queue.

		A new record has nothing to name yet, so it says what it will be. The
		others name the record they are about, captured now so a queue need not
		load every referenced document -- and, for a deletion, so the request
		still says what it removed once the record is gone.
		"""
		if self.is_new_record:
			self.reference_name = None
			self.reference_title = _("New {0}").format(_(self.reference_doctype))
			return
		if not self.reference_name:
			frappe.throw(_("A {0} request has to name the record it is about.").format(_(self.request_type)))
		self.reference_title = registry.title_of(self.reference_doctype, self.reference_name)

	def validate_raiser(self) -> None:
		"""Whose record this may be raised against.

		Read permission first, and for everyone. A request carries the record's
		current values -- the controller captures them, and the requester reads them
		back in the diff -- so being allowed to raise one against a record is being
		allowed to read that record. Without this check, a user the site withholds a
		record from could recover its contents a field at a time by proposing changes
		to it: the same leak as reading it outright, taking one extra step.

		Then whose it is: your own, or one you could have edited directly -- HR
		raising a request on an employee's behalf after a phone call is a real case,
		and it costs them nothing they did not already have. Anyone else is refused:
		a self-service form that can name a record is a self-service form that can
		name the wrong one.

		Only while the request is still open. At approval this runs in the
		*approver's* session, where the record is somebody else's and the question
		being asked is a different one -- whether they may write it, which
		`on_submit` asks directly.
		"""
		if self.is_new_record:
			# There is no record to read or own yet, so the question is whether
			# this user owns anything of the type that would own it -- an employee,
			# for a bank account. Resolved now rather than at approval, because by
			# then the session is the approver's and resolving it there would
			# attach the new record to the wrong person.
			owner = registry.owner_value(self.reference_doctype)
			if not owner:
				frappe.throw(
					_("You have nothing for a new {0} to belong to.").format(_(self.reference_doctype)),
					frappe.PermissionError,
				)
			self.record_owner = owner
			return
		if not frappe.has_permission(self.reference_doctype, "read", doc=self.reference_name):
			frappe.throw(
				_("You do not have access to that {0} record.").format(_(self.reference_doctype)),
				frappe.PermissionError,
			)
		if registry.session_owns(self.reference_doctype, self.reference_name):
			return
		if frappe.has_permission(self.reference_doctype, "write", doc=self.reference_name):
			return
		frappe.throw(
			_("You can only propose changes to your own {0} record.").format(_(self.reference_doctype)),
			frappe.PermissionError,
		)

	def validate_rows(self) -> None:
		"""Every row names a field that may be proposed, once, with a valid value.

		Checked here rather than left to the referenced record's save at approval,
		because the person who can fix a bad row is the one looking at the form now
		-- not the approver meeting the error days later on somebody else's behalf,
		with nothing to do about it but turn the request down.
		"""
		if self.is_deletion:
			# A deletion is about the record, not its fields. Rows are cleared
			# rather than refused: a form that collected some before the mode was
			# switched should not have to be rebuilt to submit.
			self.changes = []
			return
		# The same allowlist either way: a new record may set exactly the fields an
		# existing one may have corrected, which is what stops a creation form
		# being a way around it.
		allowed = registry.proposable_fields(self.reference_doctype)
		meta = frappe.get_meta(self.reference_doctype)
		seen: set[str] = set()

		for row in self.changes:
			if row.fieldname not in allowed:
				frappe.throw(
					_("Row {0}: {1} is not a field you can propose a change to.").format(
						row.idx, frappe.bold(row.label or row.fieldname)
					),
					frappe.PermissionError,
				)
			if row.fieldname in seen:
				frappe.throw(
					_("Row {0}: {1} is proposed twice. Keep one row per field.").format(
						row.idx, frappe.bold(row.label or row.fieldname)
					)
				)
			seen.add(row.fieldname)

			field = meta.get_field(row.fieldname)
			# The label as the site words it today, stored on the row so a settled
			# request still reads the way it was raised after a relabel.
			row.label = _(field.label) if field.label else row.fieldname
			self.validate_select(row, field)

	def validate_select(self, row, field) -> None:
		"""A Select's proposal has to be one of its options.

		`proposed_value` is Small Text, so nothing about the row itself stops a
		free-text answer to a closed question. The record's own save would refuse
		it eventually; asking now means the requester sees it while the dropdown
		that produced it is still in front of them.
		"""
		if field.fieldtype != "Select":
			return
		value = normalized(row.proposed_value)
		options = [option.strip() for option in (field.options or "").split("\n") if option.strip()]
		if value is None or not options or value in options:
			return
		frappe.throw(
			_("Row {0}: {1} must be one of {2}.").format(
				row.idx, frappe.bold(row.label or row.fieldname), ", ".join(options)
			)
		)

	def capture_current_values(self) -> None:
		"""Record what the referenced record says right now, for every row.

		One read of the whole record rather than one per row. Re-read on every
		validate -- including the one inside `submit()` -- so the before-and-after
		an approved request preserves is the change that was actually made, not
		the one that was proposed against a record somebody has since edited.
		"""
		if not self.changes:
			return
		if self.is_new_record:
			# Nothing precedes a record that does not exist. Said explicitly rather
			# than left to a lookup returning nothing, so the diff reads as "blank
			# to something" on purpose.
			for row in self.changes:
				row.current_value = None
			return
		fieldnames = list({row.fieldname for row in self.changes})
		current = (
			frappe.db.get_value(self.reference_doctype, self.reference_name, fieldnames, as_dict=True) or {}
		)
		for row in self.changes:
			row.current_value = normalized(current.get(row.fieldname))

	def validate_something_proposed(self) -> None:
		"""Refuse a request that asks for nothing.

		A form that lets you press Send without editing anything produces requests
		that cost an approver a decision and change nothing -- and, once approved,
		a history of changes that did not happen. A deletion is exempt: naming the
		record *is* the request.
		"""
		if self.is_deletion:
			return
		if any(normalized(row.proposed_value) != normalized(row.current_value) for row in self.changes):
			return
		frappe.throw(
			_("Fill in at least one field before sending this.")
			if self.is_new_record
			else _("Nothing is being changed. Edit at least one field before sending this.")
		)

	def on_submit(self) -> None:
		"""Approval: do the thing the request asked for.

		The only place in this section that touches the referenced doctype, and it
		does it as an ordinary permission-checked save in the approver's own
		session. `check_permission` first so a refusal names the right rather than
		the document, and `save()`/`insert()`/`delete_doc()` rather than raw writes
		so the doctype's own validation runs on the values exactly as it would
		have if the responsible team had typed them in the desk.
		"""
		if self.is_deletion:
			self.delete_record()
		elif self.is_new_record:
			self.insert_record()
		else:
			self.apply_to_record()

		# Who settled it, and -- for a site running no Workflow, where submitting
		# *is* approving -- a status that says so. `db_set` because the document
		# has already been written by the time `on_submit` runs; a second `save()`
		# here would recurse through submit.
		self.db_set("reviewed_by", frappe.session.user, update_modified=False)
		if self.status == PENDING:
			self.db_set("status", APPROVED, update_modified=False)

	def insert_record(self) -> None:
		"""Create the record this request asked for, owned by whoever asked.

		The owner comes from `record_owner`, captured when the request was raised.
		Resolving it here would resolve it in the approver's session and attach
		the record to them, which is the one mistake that would be silent.

		Permission is checked against the doctype rather than a document, because
		there is no document yet -- `insert()` checks it again anyway, and this
		makes the refusal name creating rather than writing.
		"""
		self.check_links_exist()

		policy = registry.policy(self.reference_doctype)
		record = frappe.new_doc(self.reference_doctype)
		record.update(
			{
				policy["owner_field"]: self.record_owner,
				**(policy.get("filters") or {}),
				**{row.fieldname: normalized(row.proposed_value) for row in self.changes},
			}
		)
		record.insert()
		# The request stops being about a hypothetical record and starts being the
		# history of a real one.
		self.db_set("reference_name", record.name, update_modified=False)
		self.db_set(
			"reference_title",
			registry.title_of(self.reference_doctype, record.name),
			update_modified=False,
		)
		frappe.msgprint(_("Created {0}.").format(record.name), alert=True)

	def check_links_exist(self) -> None:
		"""Refuse an approval whose free-form values name nothing yet.

		A free-form field exists because the document it points at may not exist
		when the request is raised -- see `free_text` on `Self Service Field`.
		Approving it is the moment somebody decided the value is right, and the
		linked document has to be there for the save to accept it.

		Frappe would refuse it anyway, with a message about a link. This says
		which field, which value, and what to do about it, because the approver
		is the one who can do it.

		The form says the same thing before the decision -- see `onload`, which
		reads `missing_links`, and the client script, which offers the desk's own
		new-record popup against it. This stays the guard rather than the notice:
		the check has to sit on the write, or an approval arriving by any other
		route would apply a value pointing at nothing.
		"""
		missing = self.missing_links()
		if not missing:
			return
		first = missing[0]
		frappe.throw(
			_("Create the {0} named {1} first, then approve this — {2} has no such record yet.").format(
				frappe.bold(first["target"]),
				frappe.bold(first["value"]),
				_(first["target"]),
			)
			if len(missing) == 1
			else _("These need creating before this can be approved: {0}").format(
				", ".join(f"{row['label']} → {row['value']} ({row['target']})" for row in missing)
			),
			frappe.LinkValidationError,
		)

	def missing_links(self) -> list[dict]:
		"""Every free-form value on this request that names a document not there yet.

		Two callers, and the split between them is the point. `check_links_exist`
		reads it to refuse an approval; `onload` reads it so the form can say the
		same thing while there is still time to act on it. One answer, so the
		notice and the refusal cannot come to disagree.

		Each row carries what the desk needs to offer the popup: the doctype, the
		value, the field the value would become the name of, whether creating one
		is this user's to do, and anything already on file that looks like it.

		Only a `Link` has a target this can resolve. A `Dynamic Link` names its
		doctype in a sibling field on the referenced record, so it is left to that
		record's own save, which has the sibling to hand.
		"""
		meta = frappe.get_meta(self.reference_doctype)
		free_form = {
			row["fieldname"]
			for row in registry.policy(self.reference_doctype)["fields"]
			if row.get("free_text")
		}
		missing = []
		for row in self.changes:
			value = normalized(row.proposed_value)
			if not value or row.fieldname not in free_form:
				continue
			field = meta.get_field(row.fieldname)
			target = field.options if field and field.fieldtype == "Link" else None
			if not target or frappe.db.exists(target, value):
				continue
			name_field = name_field_of(target)
			missing.append(
				{
					"fieldname": row.fieldname,
					"label": row.label or row.fieldname,
					"target": target,
					"value": value,
					# Which field the value would land in, and so what the document
					# would answer to afterwards.
					"name_field": name_field,
					# Whether this user can close the gap from here at all. The
					# popup checks it again on insert; this is what decides whether
					# to offer one.
					"creatable": bool(name_field) and bool(frappe.has_permission(target, "create")),
					"suggestions": near_matches(target, value),
				}
			)
		return missing

	def delete_record(self) -> None:
		"""Remove the record this request asked to have removed.

		No force and no cascade. A record something else links to refuses to go,
		and that refusal is the right answer -- it means the record is still in
		use, which is precisely what the person asking could not see. The approver
		gets Frappe's own link-exists message and can act on it.
		"""
		name = self.reference_name
		frappe.delete_doc(self.reference_doctype, name)
		frappe.msgprint(_("Deleted {0}.").format(self.reference_title or name), alert=True)

	def apply_to_record(self) -> None:
		"""Write the proposed values onto the referenced record.

		Rows that no longer change anything are skipped rather than written. The
		usual cause is the correction having already been applied by hand while
		the request sat in the queue, and re-writing an identical value would put
		a meaningless entry in the record's change history.
		"""
		record = frappe.get_doc(self.reference_doctype, self.reference_name)
		record.check_permission("write")

		self.check_links_exist()

		applied = []
		for row in self.changes:
			value = normalized(row.proposed_value)
			if normalized(record.get(row.fieldname)) == value:
				continue
			record.set(row.fieldname, value)
			applied.append(row.label or row.fieldname)

		if applied:
			record.save()

		frappe.msgprint(
			_("Updated {0} on {1}.").format(", ".join(applied), self.reference_title or self.reference_name)
			if applied
			else _("{0} already held these values, so nothing was changed.").format(
				self.reference_title or self.reference_name
			),
			alert=True,
		)

	def on_cancel(self) -> None:
		"""Cancelling an approved request does not put the old values back.

		Deliberate, and the reason this method exists at all rather than being
		absent. The change has been live on the record since it was approved, and
		other things -- a payslip, a letter, an export -- may have been produced
		from it since. Undoing it silently would be a second unreviewed change,
		which is the thing this doctype exists to prevent. A reversal is a new
		request, proposing the old values, with somebody's name on the decision.

		`status` is left alone: it is the Workflow's state field where a site runs
		one, and the `Reversed` state it moves to is the site's to name. Where no
		workflow runs, `docstatus` is what says this was cancelled -- see
		`status_display` in `commons.self_service.api`, which reads it rather
		than the status field for exactly this case.

		A cancelled creation does not delete what it created, and a cancelled
		deletion cannot bring anything back. Both for the same reason as a
		cancelled change: the world has moved on since approval, and undoing it
		silently would be a second unreviewed act.
		"""
