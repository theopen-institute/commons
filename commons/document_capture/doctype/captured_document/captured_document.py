"""One scan waiting to become a draft, and what Claude read off it.

The record is the scan's holding place, from the moment it arrives until a
person has made a draft from it or thrown it away. What happens to it is in
`commons.document_capture.capture`, and this controller only keeps the record
consistent with itself.

The statuses, in the order a capture usually passes through them:

* `Received`: an email created it, and its attachments have not been sorted
  yet. `capture.sort_email` settles it within moments.
* `Unread`: arrived, and waiting for somebody to press Read. Every capture
  starts here, uploaded or emailed: nothing is read, and billed, until a
  person asks. An email with no PDF or image on it waits here too, with
  `error` saying so.
* `Queued`, `Reading`: a background job has it. Claude's reading is billed,
  so there is only ever one job per capture.
* `Read`: `extracted` holds what Claude copied, waiting for a person to check it
  against the scan and make the draft.
* `Failed`: the reading went wrong, and `error` says how. The scan is kept, so
  it can be read again without being sent again.
* `Drafted`: a draft was made from it, `draft_doctype` and `draft_name` say
  which, and the scan is attached to that draft too.
* `Discarded`: somebody decided it was not worth a draft. Kept rather than
  deleted, so the email it came from still points at something.
"""

import frappe
from frappe import _
from frappe.model.document import Document

# A capture in these statuses has a job that may still write to it, or has
# already become a draft, so what it is and what it holds are settled.
SETTLED = ("Queued", "Reading", "Drafted")


class CapturedDocument(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		communication: DF.Link | None
		document_type: DF.Literal["Purchase Invoice", "Expense Claim"]
		draft_doctype: DF.Link | None
		draft_name: DF.DynamicLink | None
		email_account: DF.Link | None
		error: DF.SmallText | None
		extracted: DF.JSON | None
		model: DF.Data | None
		queued_at: DF.Datetime | None
		read_at: DF.Datetime | None
		read_started: DF.Datetime | None
		scan: DF.Attach | None
		sender: DF.Data | None
		sender_name: DF.Data | None
		source: DF.Literal["Upload", "Email"]
		status: DF.Literal[
			"Received", "Unread", "Queued", "Reading", "Read", "Failed", "Drafted", "Discarded"
		]
		subject: DF.Data | None
	# end: auto-generated types

	def before_insert(self):
		# Frappe's inbound mail makes the record with only the sender and the
		# account filled in (`InboundMail._create_reference_document`), before
		# the email's attachments are saved. Marked so `capture.sort_email` can
		# tell it from an upload, and from a capture a reply was threaded onto.
		if self.email_account and not self.scan and not self.flags.sorted_email:
			self.source = "Email"
			self.status = "Received"

	def after_insert(self):
		if self.status == "Received":
			from commons.document_capture import capture

			capture.queue_email_sorting(self.name)

	def validate(self):
		self._validate_kind()
		before = self.get_doc_before_save()
		if not before:
			return
		changed = [field for field in ("document_type", "scan") if self.has_value_changed(field)]
		if not changed:
			return
		if before.status in SETTLED:
			frappe.throw(
				_("{0} can no longer be changed: this capture is {1}.").format(
					_(self.meta.get_label(changed[0])), _(before.status).lower()
				)
			)
		# A reading is of one scan, as one kind. Another scan or another kind
		# makes it the wrong reading, so the capture is unread again.
		if before.status in ("Read", "Failed"):
			self.status = "Unread"
			self.extracted = None
			self.model = None
			self.read_at = None
			self.error = None

	def _validate_kind(self):
		"""The kind is one this site captures, when it is chosen: on a new
		capture, or a change of kind. The Select offers every kind; Document
		Capture Settings says which are switched on. An email's capture is
		left alone until `capture.sort_email` has given it the account's kind,
		which refuses a disabled one there."""
		if self.status == "Received":
			return
		if not self.is_new() and not self.has_value_changed("document_type"):
			return
		from commons.document_capture import capture

		if self.document_type not in capture.enabled_kinds():
			frappe.throw(_("This site does not capture scans as {0}.").format(_(self.document_type)))
