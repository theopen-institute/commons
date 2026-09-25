"""A Notification whose email is an Email Template.

Core's Notification writes its own subject and message, so a letter that is
also sent by hand from the form's Email menu had to be written twice and kept
the same by hand. `email_template` on Notification (a fixture) names a template
instead: its body is sent in place of the Notification's Message, and its
subject stands in when the Notification's own Subject is left blank -- which is
still the one to fill in when a list of notifications should say what each
one is about, or the email's subject should differ from the letter's.

Only the content. Who the email goes to, from which account, with which print,
and when, are still the Notification's: that is what a Notification is for, and
a template's Form Button settings are about a person sending it by hand.

The two write their Jinja differently. A template is written against the
document's fields (`{{ program }}`), because that is what the composer renders
it with; a Notification's message against `{{ doc.program }}`, `alert` and
`comments`. The template is rendered with both, the document's fields at the
top and the Notification's names over them, so a template works unchanged in
either place. Its account signature and footer are there too for an HTML
template, as the composer gives them.

How: for one call, the template's subject and body stand in for the
Notification's own, and core does the rest -- recipients, sender, attachments,
the Communication, the queue. Nothing of core's sending is copied here.

Two more things a Notification can say, both for a receipt sent on submit
(`commons.email_extensions.scheduled` has the rest):

* **Delay Sending (minutes)** -- its email waits that long in the queue, and is
  taken back if the document is cancelled meanwhile.
* **Once Across Amendments** -- a document amended from one this Notification
  already emailed about is not emailed again. Correcting a submitted payment
  is cancel, amend and submit, and the payer should hear about the payment
  once, not once per correction. A condition of `not doc.amended_from` would
  go too far: if the first email was taken back with its cancelled document,
  the corrected one is the only receipt there will be.
"""

from contextlib import contextmanager

import frappe
from frappe import _
from frappe.utils import now_datetime

from commons.email_extensions import scheduled
from commons.email_extensions.api import TEMPLATE

FIELD = "email_template"


def template_context(doc, context: dict, template, sender: str | None = None) -> dict:
	"""What a template is rendered with inside a Notification: the document's fields, then core's names."""
	values = frappe.parse_json(frappe.as_json(doc.as_dict()))
	values.update(context)
	if template.use_html:
		values = template.inject_email_account(values, sender=sender)
	return values


class TemplateNotificationMixin:
	@contextmanager
	def _template_content(self, doc, context: dict):
		"""The template's subject and body in place of this Notification's own, and what to render them with."""
		template = frappe.get_cached_doc(TEMPLATE, self.get(FIELD))
		subject, message = self.subject, self.message
		self.subject = subject or template.subject
		self.message = template.response_
		try:
			yield template_context(doc, context, template, sender=self.get("sender_email"))
		finally:
			self.subject, self.message = subject, message

	def send_an_email(self, doc, context):
		since = now_datetime()
		if not self.get(FIELD):
			result = super().send_an_email(doc, context)
		else:
			with self._template_content(doc, context) as merged:
				result = super().send_an_email(doc, merged)
		scheduled.mark_sent(self, doc, since)
		return result

	def send(self, doc):
		if self.get(scheduled.ONCE_FIELD) and self.channel == "Email" and self._sent_for_earlier_version(doc):
			return
		return super().send(doc)

	def _sent_for_earlier_version(self, doc) -> bool:
		"""Whether this Notification emailed about a version `doc` was amended from.

		Only an email that went out, or is still due to, counts: one taken back
		with its cancelled document was deleted (`scheduled.take_back`), so a
		corrected payment whose first receipt never left still sends one.
		"""
		name, seen = doc.get("amended_from"), set()
		while name and name not in seen and len(seen) < 50:
			seen.add(name)
			if frappe.db.exists(
				"Communication",
				{"reference_doctype": doc.doctype, "reference_name": name, scheduled.MARK_FIELD: self.name},
			):
				return True
			name = frappe.db.get_value(doc.doctype, name, "amended_from")
		return False

	def validate(self):
		super().validate()
		if self.get(FIELD) and self.channel != "Email":
			frappe.throw(_("An Email Template can only be used by a Notification sent by Email."))

	# The preview dialog on the form. Core's builds its own context, without the
	# document's fields at the top, so these are core's two with the template's
	# content and context swapped in.

	def _preview_context(self, preview_document):
		doc = frappe.get_cached_doc(self.document_type, preview_document)
		from frappe.email.doctype.notification.notification import get_context

		context = get_context(doc)
		context.update({"alert": self, "comments": None})
		if doc.get("_comments"):
			context["comments"] = frappe.parse_json(doc.get("_comments"))
		return doc, context

	@frappe.whitelist()
	def preview_message(self, preview_document: str | int):
		if not self.get(FIELD):
			return super().preview_message(preview_document)
		try:
			doc, context = self._preview_context(preview_document)
			with self._template_content(doc, context) as merged:
				return frappe.render_template(self.message, merged)
		except Exception as e:
			return _("Failed to render message: {}").format(str(e))

	@frappe.whitelist()
	def preview_subject(self, preview_document: str | int):
		if not self.get(FIELD):
			return super().preview_subject(preview_document)
		try:
			doc, context = self._preview_context(preview_document)
			with self._template_content(doc, context) as merged:
				return frappe.render_template(self.subject, merged) if "{" in self.subject else self.subject
		except Exception as e:
			return _("Failed to render subject: {}").format(str(e))
