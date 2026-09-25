"""Which templates a form offers, and what one fills the composer with.

Two halves, and only the second is a request:

* `extend_bootinfo` hands the desk every template that names a doctype, read as
  the user, so a form can draw its Email menu without asking. The list is small
  (one row per template) and a template saved in the same tab is folded into it
  by the desk, so a reload is only needed for one saved somewhere else.
* `compose` is what a menu item asks when it is picked: the subject and body
  rendered against the record, the recipients, the sender and the print.

The record is read from the database, not taken from the form. A form's unsaved
edits would be the only thing gained, and the price would be letting the caller
name the values `recipients` follows links from -- which is a way of looking up
the email address of any record at all. The desk says so when the form is dirty.
"""

import frappe
from frappe import _
from frappe.utils import validate_email_address

TEMPLATE = "Email Template"

# The fields a template holds for this module. Their definitions are fixtures.
DOCTYPE_FIELD = "email_doctype"
RECIPIENT_FIELD = "custom_recipient_fieldname"
SENDER_FIELD = "custom_sending_account"
ATTACH_FIELD = "attach_document_print"
PRINT_FORMAT_FIELD = "custom_print_format"
CONDITION_FIELD = "email_condition"

# Where a linked record keeps its address, tried in this order before any other
# field of the Email type. Covers the doctypes templates here point at through a
# link: Student, Employee, Customer, Supplier, Contact, Guardian.
ADDRESS_FIELDS = (
	"email_id",
	"email",
	"student_email_id",
	"prefered_email",
	"company_email",
	"personal_email",
	"email_address",
)


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Tell the desk which templates each doctype's forms offer.

	Empty, rather than an error, on a site whose fields haven't been migrated
	in yet: code lands before migrate runs, and the boot must not fail in
	between.
	"""
	meta = frappe.get_meta(TEMPLATE)
	if not (meta.has_field(DOCTYPE_FIELD) and meta.has_field(CONDITION_FIELD)):
		bootinfo.commons_email_templates = []
		return
	bootinfo.commons_email_templates = frappe.get_list(
		TEMPLATE,
		filters={DOCTYPE_FIELD: ["is", "set"]},
		fields=["name", DOCTYPE_FIELD, CONDITION_FIELD],
		order_by="name asc",
		limit_page_length=0,
	)


@frappe.whitelist(methods=["POST"])
def compose(template: str, doctype: str, name: str) -> dict:
	"""What the composer opens with, for `template` sent about one saved record.

	Asked of someone who may email the record, which is the permission core's
	own `make` checks before it sends -- so a user who could not send it is not
	shown a draft they cannot send either.
	"""
	if not frappe.has_permission(doctype, "email", doc=name):
		frappe.throw(_("Not permitted to send email about this {0}.").format(_(doctype)), frappe.PermissionError)

	settings = frappe.get_doc(TEMPLATE, template)
	settings.check_permission("read")
	if settings.get(DOCTYPE_FIELD) != doctype:
		frappe.throw(_("Email Template {0} is not written for {1}.").format(template, _(doctype)))

	record = frappe.get_doc(doctype, name)
	sender = sender_of(settings.get(SENDER_FIELD))
	# Rendered from the record as JSON, which is how core's composer sends it
	# and so what templates are written against: `{{ posting_date[0:10] }}`
	# slices a string, and a datetime can't be sliced.
	context = frappe.parse_json(frappe.as_json(record.as_dict()))
	rendered = settings.get_formatted_email(context, sender=sender)

	attach = bool(settings.get(ATTACH_FIELD))
	return {
		"subject": rendered["subject"],
		"message": rendered["message"],
		"use_html": bool(settings.use_html),
		"recipients": recipients(record, settings.get(RECIPIENT_FIELD)),
		"sender": sender,
		"attach_document_print": attach,
		"print_format": settings.get(PRINT_FORMAT_FIELD) if attach else None,
	}


def sender_of(account: str | None) -> str | None:
	"""The address an Email Account sends from, if it sends at all."""
	if not account:
		return None
	values = frappe.db.get_value("Email Account", account, ["email_id", "enable_outgoing"], as_dict=True)
	if not values or not values.enable_outgoing:
		return None
	return values.email_id


def recipients(record, fieldnames: str | None) -> list[str]:
	"""The addresses the named fields of `record` lead to, in the order named.

	A field's value is used as it stands when it is one or more addresses. When
	it is not, and the field is a Link or a Dynamic Link, the address is read off
	the record it points at (`address_of`) -- a Payment Entry's `party` names an
	Employee as `HR-EMP-00008`, and the old per-doctype scripts put exactly that
	in the To box. Anything else is skipped, so a template naming a field that
	is empty on this record opens with that recipient missing, not with an error.

	The linked record is read without checking that the user may read it. The
	template's author chose the path, and the address is the one thing read,
	which the sender has to see to send the email anyway.
	"""
	meta = frappe.get_meta(record.doctype)
	found: list[str] = []
	for fieldname in (part.strip() for part in (fieldnames or "").split(",")):
		value = record.get(fieldname) if fieldname else None
		if not value or not isinstance(value, str):
			continue
		addresses = addresses_in(value)
		df = meta.get_field(fieldname)
		if not addresses and df and df.fieldtype in ("Link", "Dynamic Link"):
			target = df.options if df.fieldtype == "Link" else record.get(df.options)
			addresses = address_of(target, value)
		found.extend(address for address in addresses if address not in found)
	return found


def addresses_in(value: str) -> list[str]:
	"""The valid addresses in a comma-separated value; empty when there are none."""
	valid = validate_email_address(value.replace(";", ","))
	return [part.strip() for part in valid.split(",") if part.strip()] if valid else []


def address_of(doctype: str | None, name: str) -> list[str]:
	"""Where to write to about the record `doctype`/`name`.

	The record's own address, by `ADDRESS_FIELDS` first and then any other field
	of the Email type in form order; failing that, the default Contact's.
	"""
	if not doctype or not frappe.db.exists("DocType", doctype) or not frappe.db.exists(doctype, name):
		return []

	meta = frappe.get_meta(doctype)
	email_fields = [df.fieldname for df in meta.fields if df.fieldtype == "Data" and df.options == "Email"]
	candidates = [f for f in ADDRESS_FIELDS if meta.has_field(f)]
	candidates += [f for f in email_fields if f not in candidates]
	if candidates:
		values = frappe.db.get_value(doctype, name, candidates, as_dict=True) or {}
		for fieldname in candidates:
			if addresses := addresses_in(values.get(fieldname) or ""):
				return addresses[:1]

	from frappe.contacts.doctype.contact.contact import get_default_contact

	if contact := get_default_contact(doctype, name):
		return addresses_in(frappe.db.get_value("Contact", contact, "email_id") or "")
	return []
