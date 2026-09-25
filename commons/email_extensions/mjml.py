"""Email Templates designed in MJML, and sent as the responsive HTML it compiles to.

A template with "Design with MJML" ticked keeps its MJML in `mjml_source`, and
every save compiles that into `response_html` with "Use HTML" ticked -- so
everything that already reads a template (the form's Email menu, core's
composer, a workflow state's email, a Notification) sends the compiled HTML and
none of them has to know MJML exists. Compiling on save rather than on send
means a send costs nothing extra, and a layout that doesn't compile is refused
while its author is looking at it rather than failing somebody's email later.

The compiled HTML is a complete document, `<!doctype html>` and all, and Frappe
wraps every email in `templates/emails/standard.html` unless told the message
is raw -- which only the composer can say. `commons/templates/emails/standard.html`
is what lets such a document through whichever way it is sent; its comment says
how.

Compiled first, rendered later
------------------------------
Jinja is filled in when the email is sent, against the document; MJML is
compiled when the template is saved, before there is a document. So the Jinja
has to survive the compiler, and on its own it does not: mrml is a strict XML
parser, and `{% if total < 100 %}` or a bare `&` stop it. Every Jinja tag is
therefore swapped for an inert placeholder before compiling and put back
after, which also means a `{% for %}` may wrap whole `<mj-section>`s without
the `<mj-raw>` MJML would otherwise want around it.

mrml drops what it doesn't recognise -- an unknown tag, or `<mj-text>` straight
under `<mj-body>` -- without a word. The preview on the template's form is
where that shows.
"""

import re

import frappe
from frappe import _

from commons.email_extensions.api import TEMPLATE

USE_FIELD = "use_mjml"
SOURCE_FIELD = "mjml_source"

JINJA = re.compile(r"\{\{.*?\}\}|\{%.*?%\}|\{#.*?#\}", re.S)
PLACEHOLDER = re.compile(r"CMJINJA(\d+)X")
# An ampersand that does not begin an entity: `Fees & Charges`.
BARE_AMPERSAND = re.compile(r"&(?![A-Za-z][A-Za-z0-9]*;|#[0-9]+;|#[xX][0-9A-Fa-f]+;)")

# Every email passes through premailer on its way out, and premailer (through
# lxml) drops MJML's lowercase `<!doctype html>` while keeping the same
# declaration in capitals. Without one a client may render in quirks mode.
DOCTYPE_HTML5 = re.compile(r"^\s*<!doctype html>", re.I)
DOCTYPE = "<!DOCTYPE html>"


class MJMLError(Exception):
	pass


def to_html(source: str) -> tuple[str, list[str]]:
	"""The HTML `source` compiles to, with its Jinja intact, and mrml's warnings."""
	import mrml

	saved: list[str] = []

	def keep(match: re.Match) -> str:
		saved.append(match.group(0))
		return f"CMJINJA{len(saved) - 1}X"

	protected = BARE_AMPERSAND.sub("&amp;", JINJA.sub(keep, source or ""))
	try:
		output = mrml.to_html(protected)
	except Exception as e:
		raise MJMLError(str(e)) from e

	html = PLACEHOLDER.sub(lambda m: saved[int(m.group(1))], output.content)
	return DOCTYPE_HTML5.sub(DOCTYPE, html, count=1), [str(w) for w in output.warnings]


def compile_template(doc, method=None) -> None:
	"""`before_validate` on Email Template: write the compiled HTML over `response_html`.

	Before core's own `validate`, so the Jinja check it runs on the response is
	run on what will actually be sent.
	"""
	if not doc.get(USE_FIELD):
		return
	if not (doc.get(SOURCE_FIELD) or "").strip():
		frappe.throw(_("Write the template's MJML, or untick Design with MJML."))
	try:
		html, warnings = to_html(doc.get(SOURCE_FIELD))
	except MJMLError as e:
		frappe.throw(_("The MJML could not be compiled: {0}").format(e), title=_("MJML"))
	doc.use_html = 1
	doc.response_html = html
	if warnings:
		frappe.msgprint("<br>".join(frappe.utils.escape_html(w) for w in warnings), title=_("MJML warnings"))


@frappe.whitelist(methods=["POST"])
def preview(source: str, email_doctype: str | None = None, document: str | None = None) -> dict:
	"""The template compiled, and rendered against a document of `email_doctype` if one can be read.

	`document` when the form names one, otherwise the most recently modified the
	user may read. The rendering is only as good as that document: a field it
	leaves empty previews empty.
	"""
	frappe.has_permission(TEMPLATE, "write", throw=True)
	try:
		html, warnings = to_html(source)
	except MJMLError as e:
		return {"error": str(e)}

	result = {"html": html, "warnings": warnings, "document": None}
	if not email_doctype or not frappe.db.exists("DocType", email_doctype):
		return result

	if document:
		if not frappe.has_permission(email_doctype, "read", doc=document):
			document = None
	else:
		latest = frappe.get_list(email_doctype, pluck="name", order_by="modified desc", limit=1)
		document = latest[0] if latest else None
	if not document:
		return result

	record = frappe.get_doc(email_doctype, document)
	context = frappe.parse_json(frappe.as_json(record.as_dict()))
	template = frappe.get_doc({"doctype": TEMPLATE, "subject": "", "use_html": 1, "response_html": html})
	try:
		result["html"] = template.get_formatted_email(context)["message"]
		result["document"] = document
	except Exception as e:
		result["render_error"] = str(e)
	return result
