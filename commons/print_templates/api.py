"""Rendering a Web Template for print, and the form's Test PDF and Fill from a Record.

See the package docstring for what the fields are and why.
"""

import base64
import json

import frappe
from frappe import _

TEMPLATE = "Web Template"
PREP_FIELD = "context_prep"
TEST_FIELD = "test_values"
# Core's own gate for authoring sandboxed Python: see `ServerScript.validate`.
SCRIPT_ROLE = "Script Manager"


def run_prep(code: str | None, doc, label: str) -> dict:
	"""What `code` sets `values` to with `doc` in scope; `{"doc": doc}` when there is no code.

	`doc` goes in the globals rather than beside `values`, so that a function the
	prep defines can read it too -- exec'd code only sees its globals from inside
	a def.
	"""
	if not (code or "").strip():
		return {"doc": doc}

	from frappe.utils.safe_exec import safe_exec

	scope = {"values": {}}
	safe_exec(
		code,
		{"doc": doc},
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


def render_web_template(name: str, doc=None, values: dict | None = None) -> str:
	"""Jinja: Web Template `name` rendered for `doc`, through its Context Prep.

	Pass `values` instead to skip the prep and hand the template its variables
	directly. Rendered as the template itself, with none of the website section
	markup `web_block` wraps around one.
	"""
	template = frappe.get_cached_doc(TEMPLATE, name)
	if values is None:
		values = run_prep(template.get(PREP_FIELD), doc, name)
	return template.render(values)


def validate_template(doc, method=None) -> None:
	"""`validate` on Web Template: who may change the prep, and that both fields parse."""
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

	parse_test_values(doc.get(TEST_FIELD))


def parse_test_values(text: str | None) -> dict:
	if not (text or "").strip():
		return {}
	try:
		values = json.loads(text)
	except ValueError as e:
		frappe.throw(_("Test Values is not valid JSON: {0}").format(e), title=_("Test Values"))
	if not isinstance(values, dict):
		frappe.throw(_("Test Values must be a JSON object, one key per template variable."))
	return values


@frappe.whitelist(methods=["POST"])
def test_pdf(source: str | None = None, test_values: str | None = None, template: str | None = None) -> dict:
	"""A PDF of `source` rendered with `test_values`, as base64, or the error that stopped it.

	From what the form holds, saved or not. A standard template is rendered from
	its file, as a print would; its editor text is not what prints.
	"""
	frappe.has_permission(TEMPLATE, "write", throw=True)
	values = parse_test_values(test_values)

	saved = template and frappe.db.exists(TEMPLATE, template) and frappe.get_doc(TEMPLATE, template)
	if saved and saved.standard:
		web_template = saved
	else:
		web_template = frappe.get_doc({"doctype": TEMPLATE, "standard": 0, "template": source or ""})

	try:
		body = web_template.render(values)
	except Exception as e:
		return {"error": str(e)}

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
	return {"pdf": base64.b64encode(get_pdf(html)).decode()}


@frappe.whitelist(methods=["POST"])
def fill_test_values(
	doctype: str, name: str, context_prep: str | None = None, label: str | None = None
) -> str:
	"""What `context_prep` returns for one real record, as JSON for Test Values.

	The prep comes from the form rather than the saved template, so it can be
	tried before it is saved -- which is running Python handed in by the caller,
	hence the Script Manager check before anything else.
	"""
	frappe.only_for(SCRIPT_ROLE, message=True)
	record = frappe.get_doc(doctype, name)
	record.check_permission("read")
	values = run_prep(context_prep, record, label or _("(unsaved)"))
	return frappe.as_json(values, indent=2)
