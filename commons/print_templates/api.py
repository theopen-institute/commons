"""Rendering a Web Template for print, and the form's Test PDF.

See the package docstring for what the fields are and why.
"""

import base64
import json

import frappe
from frappe import _

from commons.print_templates import contract

TEMPLATE = "Web Template"
PREP_FIELD = "context_prep"
# Core's own gate for authoring sandboxed Python: see `ServerScript.validate`.
SCRIPT_ROLE = "Script Manager"


def run_prep(code: str | None, doc, label: str, inputs: dict | None = None) -> dict:
	"""What `code` sets `values` to, with the caller's `inputs` and `doc` in scope.

	Without code the template is handed the inputs themselves, and `doc` when
	there is one -- which for a template with no Fields is how it always worked.

	`inputs` and `doc` go in the globals rather than beside `values`, so that a
	function the prep defines can read them too -- exec'd code only sees its
	globals from inside a def.
	"""
	inputs = frappe._dict(inputs or {})
	if not (code or "").strip():
		values = dict(inputs)
		if doc is not None:
			values["doc"] = doc
		return values

	from frappe.utils.safe_exec import safe_exec

	scope = {"values": {}}
	safe_exec(
		code,
		{"doc": doc, "inputs": inputs},
		scope,
		restrict_commit_rollback=True,
		script_filename=f"Web Template {label}",
	)
	values = scope.get("values")
	if not isinstance(values, dict):
		frappe.throw(
			_("The Context Prep of Web Template {0} must set <code>values</code> to a dict.").format(
				frappe.bold(label)
			)
		)
	return values


def render_web_template(name: str, doc=None, values: dict | None = None, **inputs) -> str:
	"""Jinja: Web Template `name` rendered from its inputs, through its Context Prep.

	Inputs are passed by name, as the template's Fields declare them:
	`render_web_template("Student Statement", student=doc.name)`. `doc` is
	passed on to the prep as well, for a template that reads the printed
	document directly. `values` skips the prep and hands the template its
	variables as they are.

	Not checked against the Fields: a print is better made short than refused.
	Rendered as the template itself, with none of the website section markup
	`web_block` wraps around one.
	"""
	template = frappe.get_cached_doc(TEMPLATE, name)
	if values is None:
		values = run_prep(template.get(PREP_FIELD), doc, name, inputs)
	return template.render(values)


def validate_template(doc, method=None) -> None:
	"""`validate` on Web Template: who may change the prep, that it compiles, and that inputs can be checked."""
	code = doc.get(PREP_FIELD) or ""
	before = doc.get_doc_before_save()
	if code != ((before.get(PREP_FIELD) if before else "") or ""):
		frappe.only_for(SCRIPT_ROLE, message=True)
	if code.strip():
		from frappe.utils.safe_exec import FrappeTransformer
		from RestrictedPython import compile_restricted

		# Refused rather than warned about, as a Server Script's would be: a prep
		# that does not compile fails every print that goes through it.
		try:
			compile_restricted(code, policy=FrappeTransformer)
		except SyntaxError as e:
			frappe.throw(_("Context Prep does not compile: {0}").format(e), title=_("Context Prep"))

	contract.validate_fields(doc.fields)


def parse_values(text: str | dict | None, what: str = "test values") -> dict:
	"""JSON from the test dialog, which must be an object."""
	if isinstance(text, dict):
		return text
	if not (text or "").strip():
		return {}
	try:
		values = json.loads(text)
	except ValueError as e:
		frappe.throw(_("The {0} are not valid JSON: {1}").format(_(what), e), title=_("Test PDF"))
	if not isinstance(values, dict):
		frappe.throw(_("The {0} must be a JSON object.").format(_(what)))
	return values


def _prepare(template, context_prep, fields, inputs, doctype, name) -> tuple[dict, list[str]]:
	"""The prep's output for the dialog's inputs, and where the inputs miss the Fields.

	The prep is the editor's when the caller sends one -- running Python handed
	in by the caller, so only a Script Manager may -- and otherwise the saved
	template's. A record, when the dialog names one, is `doc` to the prep and
	has to be readable by whoever asks.
	"""
	fields = frappe.parse_json(fields or "[]")
	inputs = parse_values(inputs, "inputs")
	if context_prep is not None:
		frappe.only_for(SCRIPT_ROLE, message=True)
		code = context_prep
	else:
		code = frappe.db.get_value(TEMPLATE, template, PREP_FIELD) if template else None

	doc = None
	if doctype and name:
		doc = frappe.get_doc(doctype, name)
		doc.check_permission("read")

	warnings = contract.check(fields, inputs)
	return run_prep(code, doc, template or _("(unsaved)"), inputs), warnings


@frappe.whitelist(methods=["POST"])
def test_pdf(
	source: str | None = None,
	template: str | None = None,
	fields: str | list | None = None,
	inputs: str | dict | None = None,
	context_prep: str | None = None,
	doctype: str | None = None,
	name: str | None = None,
	values: str | None = None,
	letter_head: str | None = None,
) -> dict:
	"""A PDF of `source`, as base64, or the error that stopped it.

	Rendered from `values` when the dialog sends them -- prepared values edited
	by hand -- and otherwise from `inputs` through the prep, as a print would
	be. `source` is what the form's editor holds, saved or not; a standard
	template is rendered from its file, as a print would, since its editor
	text is not what prints. Nothing sent is kept. `warnings` says where the
	inputs miss the form's Fields; the PDF is made either way.

	`letter_head` puts that Letter Head above and its footer below, as Frappe's
	standard format does (`with_letter_head`).
	"""
	frappe.has_permission(TEMPLATE, "write", throw=True)
	if (values or "").strip():
		values, warnings = parse_values(values), []
	else:
		values, warnings = _prepare(template, context_prep, fields, inputs, doctype, name)

	saved = template and frappe.db.exists(TEMPLATE, template) and frappe.get_doc(TEMPLATE, template)
	if saved and saved.standard:
		web_template = saved
	else:
		web_template = frappe.get_doc({"doctype": TEMPLATE, "standard": 0, "template": source or ""})

	try:
		body = web_template.render(values)
	except Exception as e:
		return {"error": str(e), "warnings": warnings}

	if letter_head:
		doc = frappe.get_doc(doctype, name) if doctype and name else None
		body = with_letter_head(body, letter_head, doc)

	from frappe.utils.pdf import get_pdf
	from frappe.www.printview import get_print_style

	# Frappe's own print page, as `frappe.utils.print_utils.get_print` sends to
	# the PDF generator, so the test and a real print share their CSS.
	html = frappe.render_template(
		"frappe/www/printview.html",
		{
			"body": body,
			"print_style": get_print_style(),
			"title": template or _("Test PDF"),
			"lang": frappe.local.lang,
			"layout_direction": "ltr",
			"comment": frappe.session.user,
		},
	)
	return {"pdf": base64.b64encode(get_pdf(html)).decode(), "warnings": warnings}


def with_letter_head(body: str, letter_head: str, doc=None) -> str:
	"""`body` between a Letter Head and its footer, marked up as Frappe's standard format does.

	The same Jinja rendering of the letter head's content and footer, against
	`doc` where there is one, and the same `header-html`/`footer-html` markers
	when Print Settings repeats them, which is what makes wkhtmltopdf put them
	on every page (`templates/print_formats/standard.html`,
	`frappe.www.printview.get_rendered_template`).
	"""
	from frappe.utils.jinja import render_template

	head = frappe.db.get_value(
		"Letter Head", letter_head, ["content", "footer", "header_script", "footer_script"], as_dict=True
	)
	if not head:
		frappe.throw(_("Letter Head {0} not found.").format(frappe.bold(letter_head)))
	context = {"doc": doc.as_dict() if doc else {}}
	content = render_template(head.content or "", context)
	footer = render_template(head.footer or "", context)
	if content and head.header_script:
		content += f"<script>{head.header_script}</script>"
	if footer and head.footer_script:
		footer += f"<script>{head.footer_script}</script>"

	repeat = frappe.db.get_single_value("Print Settings", "repeat_header_footer")
	header_attrs = ' id="header-html" class="hidden-pdf"' if repeat else ""
	footer_attrs = ' id="footer-html" class="visible-pdf"' if repeat else ""
	return (
		f'<div{header_attrs}><div class="letter-head">{content}</div></div>'
		f"{body}"
		f'<div{footer_attrs}><div class="letter-head-footer">{footer}</div></div>'
	)


@frappe.whitelist(methods=["POST"])
def prepare_values(
	template: str | None = None,
	fields: str | list | None = None,
	inputs: str | dict | None = None,
	context_prep: str | None = None,
	doctype: str | None = None,
	name: str | None = None,
) -> dict:
	"""The prep's output for the dialog's inputs, as JSON to edit before printing.

	For a test the inputs cannot express: a made-up name, an edge case, a real
	statement with the real names taken out.
	"""
	frappe.has_permission(TEMPLATE, "write", throw=True)
	values, warnings = _prepare(template, context_prep, fields, inputs, doctype, name)
	return {"values": frappe.as_json(values, indent=2), "warnings": warnings}
