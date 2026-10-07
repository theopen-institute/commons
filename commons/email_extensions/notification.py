"""A Notification whose email is an Email Template, rendered the way the composer renders it.

Frappe's Notification has `email_template`: while one is named, the
template's subject and body are sent in place of the Notification's own
Subject and Message, which the form then hides. Core renders the template
with the document's fields alone; this module renders it with the
Notification's names as well.

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

How: core's `get_email_template_content` is answered here, and core does the
rest -- recipients, sender, attachments, the Communication, the queue, the
preview dialog and the bell. Nothing of core's sending is copied here.

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
	def get_email_template_content(self, doc):
		"""Core's template content, rendered with `doc`, `alert` and `comments` beside the document's fields."""
		if not self.get(FIELD):
			return None
		template = frappe.get_cached_doc(TEMPLATE, self.get(FIELD))
		merged = template_context(
			doc, self._notification_context(doc), template, sender=self.get("sender_email")
		)
		subject = template.subject or ""
		if "{" in subject:
			subject = frappe.render_template(subject, merged, restrict_globals=True)
		message = frappe.render_template(template.response_, merged, restrict_globals=True)
		if not message:
			frappe.throw(_("Email Template {0} has no content to send").format(self.get(FIELD)))
		return {"subject": subject, "message": message}

	def send_an_email(self, doc, context, *args, **kwargs):
		since = now_datetime()
		result = super().send_an_email(doc, context, *args, **kwargs)
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

	def _notification_context(self, doc) -> dict:
		from frappe.email.doctype.notification.notification import get_context

		context = get_context(doc)
		context.update({"alert": self, "comments": None})
		if doc.get("_comments"):
			context["comments"] = frappe.parse_json(doc.get("_comments"))
		return context
