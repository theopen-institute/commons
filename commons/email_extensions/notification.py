"""A Notification whose email is an Email Template.

Core's Notification writes its own subject and message, so a letter that is
also sent by hand from the form's Email menu had to be written twice and kept
the same by hand. `email_template` on Notification names a template instead
(Frappe's own field where it has one, else a Custom Field -- see
`sync_template_field`): its body is sent in place of the Notification's
Message, and its subject stands in when the Notification's own Subject is left
blank -- which is still the one to fill in when a list of notifications should
say what each one is about, or the email's subject should differ from the
letter's.

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

# Frappe's develop branch (after 16.x) has `email_template` on Notification
# itself, with its own sending: `send_an_email(doc, context, template_content)`
# and `get_email_template_content(doc)`. Where it does, the field is Frappe's
# and this module keeps only what it says differently -- the Notification's own
# Subject still wins over the template's, and `doc`, `alert` and `comments` are
# there to render with -- by answering `get_email_template_content`. Where it
# does not, the field is a Custom Field and the template is swapped in around
# core's `send_an_email`, as before.
FIELD_DEFINITION = {
	"fieldname": FIELD,
	"label": "Email Template",
	"fieldtype": "Link",
	"options": TEMPLATE,
	"insert_after": "message_sb",
	"depends_on": "eval:doc.channel == 'Email'",
	"is_system_generated": 1,
	"description": "Send this template's message in place of the one below. Its subject is used when Subject "
	"above is left blank. Write it against the document's fields (<code>{{ program }}</code>), as in any "
	"template; <code>doc</code>, <code>alert</code> and <code>comments</code> work too. Recipients, sender "
	"and attachments are still set here.",
}
CUSTOM_FIELD = f"Notification-{FIELD}"

# Frappe's own field hides Subject while a template is named, which would hide a
# Subject this module still sends. Its depends_on without that last clause.
NATIVE_SUBJECT_DEPENDS_ON = "eval: in_list(['Email', 'Slack', 'System Notification'], doc.channel)"


def core_has_field() -> bool:
	"""Whether this Frappe's Notification has `email_template` as a standard field."""
	return bool(frappe.db.exists("DocField", {"parent": "Notification", "fieldname": FIELD}))


def core_sends_templates() -> bool:
	"""Whether this Frappe's Notification sends an Email Template's content itself."""
	from frappe.email.doctype.notification.notification import Notification

	return hasattr(Notification, "get_email_template_content")


def sync_template_field() -> None:
	"""Put `email_template` on Notification, unless Frappe already has it there.

	Not a fixture: a fixture can only say "this Custom Field exists", and on a
	Frappe with the standard field that fails the install (a field of that name
	is already there) and, on a site upgraded into it, would leave the form with
	the field twice. The Custom Field is deleted there instead; the column is the
	same one, so every Notification keeps the template it named.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	if not core_has_field():
		if not frappe.db.exists("Custom Field", CUSTOM_FIELD):
			create_custom_field("Notification", FIELD_DEFINITION)
		return

	if frappe.db.exists("Custom Field", CUSTOM_FIELD):
		frappe.delete_doc("Custom Field", CUSTOM_FIELD, ignore_permissions=True, force=True)
	make_property_setter(
		"Notification", "subject", "depends_on", NATIVE_SUBJECT_DEPENDS_ON, "Data", validate_fields_for_doctype=False
	)
	make_property_setter(
		"Notification", FIELD, "description", FIELD_DEFINITION["description"], "Text", validate_fields_for_doctype=False
	)


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

	def get_email_template_content(self, doc):
		"""Core's hook where core sends templates itself: this module's subject and context, not core's."""
		if not self.get(FIELD):
			return None
		context = self._notification_context(doc)
		with self._template_content(doc, context) as merged:
			subject = self.subject or ""
			if "{" in subject:
				subject = frappe.render_template(subject, merged, restrict_globals=True)
			message = frappe.render_template(self.message, merged, restrict_globals=True)
		if not message:
			frappe.throw(_("Email Template {0} has no content to send").format(self.get(FIELD)))
		return {"subject": subject, "message": message}

	def send_an_email(self, doc, context, *args, **kwargs):
		since = now_datetime()
		if not self.get(FIELD) or core_sends_templates():
			result = super().send_an_email(doc, context, *args, **kwargs)
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
	# content and context swapped in. Where core sends templates itself, its
	# previews already go through `get_email_template_content` above.

	def _notification_context(self, doc) -> dict:
		from frappe.email.doctype.notification.notification import get_context

		context = get_context(doc)
		context.update({"alert": self, "comments": None})
		if doc.get("_comments"):
			context["comments"] = frappe.parse_json(doc.get("_comments"))
		return context

	def _preview_context(self, preview_document):
		doc = frappe.get_cached_doc(self.document_type, preview_document)
		return doc, self._notification_context(doc)

	@frappe.whitelist()
	def preview_message(self, preview_document: str | int):
		if not self.get(FIELD) or core_sends_templates():
			return super().preview_message(preview_document)
		try:
			doc, context = self._preview_context(preview_document)
			with self._template_content(doc, context) as merged:
				return frappe.render_template(self.message, merged)
		except Exception as e:
			return _("Failed to render message: {}").format(str(e))

	@frappe.whitelist()
	def preview_subject(self, preview_document: str | int):
		if not self.get(FIELD) or core_sends_templates():
			return super().preview_subject(preview_document)
		try:
			doc, context = self._preview_context(preview_document)
			with self._template_content(doc, context) as merged:
				return frappe.render_template(self.subject, merged) if "{" in self.subject else self.subject
		except Exception as e:
			return _("Failed to render subject: {}").format(str(e))
