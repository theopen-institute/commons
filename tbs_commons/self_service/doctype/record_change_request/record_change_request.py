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
entry in `tbs_commons.self_service.policies`. Employee is the first such entry
and currently the only one; a second HR record about the same person is a
registry entry and a page, not another copy of this file.

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

import frappe
from frappe import _
from frappe.model.document import Document

from tbs_commons.self_service import registry

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


class RecordChangeRequest(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from tbs_commons.self_service.doctype.record_change_item.record_change_item import (
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

	def validate(self) -> None:
		# Refuses an unregistered doctype outright, and does it before anything
		# else reads a policy that does not exist.
		registry.policy(self.reference_doctype)
		if self.docstatus == 0:
			self.validate_raiser()
		self.reference_title = registry.title_of(self.reference_doctype, self.reference_name)
		self.validate_rows()
		self.capture_current_values()
		self.validate_something_changed()

	def validate_raiser(self) -> None:
		"""Whose record this may be raised against.

		Your own, or one you could have edited directly -- HR raising a request on
		an employee's behalf after a phone call is a real case, and it costs them
		nothing they did not already have. Anyone else is refused: a self-service
		form that can name a record is a self-service form that can name the
		wrong one.

		Only while the request is still open. At approval this runs in the
		*approver's* session, where the record is somebody else's and the question
		being asked is a different one -- whether they may write it, which
		`apply_to_record` asks directly.
		"""
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
		fieldnames = list({row.fieldname for row in self.changes})
		current = (
			frappe.db.get_value(self.reference_doctype, self.reference_name, fieldnames, as_dict=True) or {}
		)
		for row in self.changes:
			row.current_value = normalized(current.get(row.fieldname))

	def validate_something_changed(self) -> None:
		"""Refuse a request that asks for nothing.

		A form that lets you press Send without editing anything produces requests
		that cost an approver a decision and change nothing -- and, once approved,
		a history of changes that did not happen.
		"""
		if any(normalized(row.proposed_value) != normalized(row.current_value) for row in self.changes):
			return
		frappe.throw(_("Nothing is being changed. Edit at least one field before sending this."))

	def on_submit(self) -> None:
		"""Approval: write the proposed values onto the referenced record.

		The only place in this section that writes to anything but the request
		itself, and it does it as an ordinary permission-checked save in the
		approver's own session. `check_permission` first so the refusal names the
		right rather than the document, and `save()` rather than `db_set` so the
		doctype's own validation -- email formats, select options, whatever a site
		has added -- runs on the values exactly as it would have if the
		responsible team had typed them in the desk.

		Rows that no longer change anything are skipped rather than written. The
		usual cause is the correction having already been applied by hand while the
		request sat in the queue, and re-writing an identical value would put a
		meaningless entry in the record's change history.
		"""
		record = frappe.get_doc(self.reference_doctype, self.reference_name)
		record.check_permission("write")

		applied = []
		for row in self.changes:
			value = normalized(row.proposed_value)
			if normalized(record.get(row.fieldname)) == value:
				continue
			record.set(row.fieldname, value)
			applied.append(row.label or row.fieldname)

		if applied:
			record.save()

		# Who settled it, and -- for a site running no Workflow, where submitting
		# *is* approving -- a status that says so. `db_set` because the document
		# has already been written by the time `on_submit` runs; a second `save()`
		# here would recurse through submit.
		self.db_set("reviewed_by", frappe.session.user, update_modified=False)
		if self.status == PENDING:
			self.db_set("status", APPROVED, update_modified=False)

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
		`status_display` in `tbs_commons.self_service.api`, which reads it rather
		than the status field for exactly this case.
		"""
