"""A Web Template printed through its Context Prep, and the form's two tools.

Against a site: the prep runs in Frappe's own sandbox, which reads
`server_script_enabled` from common_site_config. Every Web Template here is named `claude-probe-…` and is
inserted inside the test's transaction, which the base class rolls back.
"""

import base64
import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from commons.print_templates import api, contract

PREP = """
def name_of(d):
    return d.full_name or d.name

values = {"party": name_of(doc), "kind": doc.doctype}
"""

LAYOUT = "<h1>{{ party }}</h1><p>{{ kind }}</p>"


def template(suffix, **fields):
	return frappe.get_doc(
		{
			"doctype": "Web Template",
			"name": f"claude-probe-{suffix}",
			"type": "Component",
			"standard": 0,
			"template": LAYOUT,
			**fields,
		}
	).insert()


class TestPrintTemplates(IntegrationTestCase):
	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def test_no_prep_hands_the_template_the_document(self):
		doc = frappe.get_doc("User", "Administrator")
		self.assertEqual(api.run_prep("", doc, "x"), {"doc": doc})

	def test_the_prep_sets_values_and_its_functions_see_doc(self):
		doc = frappe.get_doc("User", "Administrator")
		self.assertEqual(
			api.run_prep(PREP, doc, "x"),
			{"party": doc.full_name or "Administrator", "kind": "User"},
		)

	def test_a_prep_that_sets_no_dict_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			api.run_prep("values = 3", frappe.get_doc("User", "Administrator"), "x")

	def test_a_print_format_renders_the_template_through_its_prep(self):
		template("render", context_prep=PREP)
		html = frappe.render_template(
			'{{ render_web_template("claude-probe-render", doc) }}',
			{"doc": frappe.get_doc("User", "Administrator")},
		)
		self.assertIn("<p>User</p>", html)

	def test_values_passed_directly_skip_the_prep(self):
		template("direct", context_prep=PREP)
		html = api.render_web_template("claude-probe-direct", values={"party": "Mock", "kind": "Test"})
		self.assertEqual(html, "<h1>Mock</h1><p>Test</p>")

	def test_only_a_script_manager_may_change_the_prep(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			frappe.get_doc(
				{
					"doctype": "Web Template",
					"name": "claude-probe-guest",
					"type": "Component",
					"template": LAYOUT,
					"context_prep": PREP,
				}
			).insert(ignore_permissions=True)

	def test_a_prep_that_does_not_compile_is_refused(self):
		with self.assertRaises(frappe.ValidationError):
			template("syntax", context_prep="values = {")

	def test_test_values_must_be_a_json_object(self):
		with self.assertRaises(frappe.ValidationError):
			api.test_pdf(source=LAYOUT, values="[1, 2]")

	def test_test_pdf_prints_the_editor_text_with_the_test_values(self):
		# The generator is stubbed: wkhtmltopdf fetches the print page's assets
		# from the site's URL, and whether that answers is the machine's business,
		# not this module's. What is checked is the page handed to it.
		with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-stub") as get_pdf:
			r = api.test_pdf(source=LAYOUT, values=json.dumps({"party": "Mock", "kind": "Test"}))
		self.assertEqual(base64.b64decode(r["pdf"]), b"%PDF-stub")
		page = get_pdf.call_args.args[0]
		self.assertIn('<div class="print-format">', page)
		self.assertIn("<h1>Mock</h1><p>Test</p>", page)

	def test_test_pdf_reports_a_template_that_does_not_render(self):
		r = api.test_pdf(source="{{ party.missing() }}", values="{}")
		self.assertIn("error", r)

	def test_inputs_are_passed_by_name_and_read_by_the_prep(self):
		template(
			"inputs",
			template="<h1>{{ name }}</h1>",
			context_prep='values = {"name": frappe.db.get_value("User", inputs.user, "first_name")}',
			fields=[
				{"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "reqd": 1}
			],
		)
		html = frappe.render_template(
			'{{ render_web_template("claude-probe-inputs", user="Administrator") }}', {}
		)
		self.assertEqual(html, "<h1>%s</h1>" % frappe.db.get_value("User", "Administrator", "first_name"))

	def test_without_a_prep_the_template_is_given_its_inputs(self):
		template("bare", template="<p>{{ party }}</p>")
		self.assertEqual(api.render_web_template("claude-probe-bare", party="Mock"), "<p>Mock</p>")

	def test_a_link_input_must_say_what_it_links_to(self):
		with self.assertRaises(frappe.ValidationError):
			template("link", fields=[{"label": "Student", "fieldtype": "Link"}])

	def test_a_link_to_nothing_is_reported(self):
		fields = [{"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "reqd": 1}]
		self.assertEqual(
			contract.check(fields, {"user": "claude-probe-nobody@example.org"}),
			['user: there is no User named "claude-probe-nobody@example.org".'],
		)

	def test_test_pdf_prints_from_inputs_through_the_prep(self):
		fields = [{"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "reqd": 1}]
		prep = 'values = {"party": inputs.user, "kind": "Input"}'
		with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-stub") as get_pdf:
			r = api.test_pdf(
				source=LAYOUT, fields=fields, inputs={"user": "Administrator"}, context_prep=prep
			)
		self.assertEqual(r["warnings"], [])
		self.assertIn("<h1>Administrator</h1><p>Input</p>", get_pdf.call_args.args[0])

	def test_test_pdf_warns_about_missing_inputs_but_still_prints(self):
		fields = [{"label": "User", "fieldname": "user", "fieldtype": "Link", "options": "User", "reqd": 1}]
		with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-stub"):
			r = api.test_pdf(source="<p>x</p>", fields=fields, inputs={}, context_prep="")
		self.assertIn("pdf", r)
		self.assertEqual(r["warnings"], ["user is required but missing."])

	def test_prepared_values_can_be_edited_and_printed_as_they_are(self):
		r = api.prepare_values(
			fields=[{"label": "User", "fieldname": "user", "fieldtype": "Data"}],
			inputs={"user": "Administrator"},
			context_prep='values = {"party": inputs.user, "kind": "Real"}',
		)
		edited = {**json.loads(r["values"]), "party": "Mock"}
		with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-stub") as get_pdf:
			api.test_pdf(source=LAYOUT, values=json.dumps(edited))
		self.assertIn("<h1>Mock</h1><p>Real</p>", get_pdf.call_args.args[0])

	def test_a_template_without_fields_reads_the_record(self):
		r = api.prepare_values(context_prep=PREP, doctype="User", name="Administrator")
		self.assertEqual(json.loads(r["values"])["kind"], "User")

	def test_a_letter_head_goes_above_and_its_footer_below(self):
		frappe.get_doc(
			{
				"doctype": "Letter Head",
				"letter_head_name": "claude-probe-letter-head",
				"source": "HTML",
				"content": "<b>HEAD {{ doc.name }}</b>",
				"footer_source": "HTML",
				"footer": "<i>FOOT</i>",
			}
		).insert()
		with patch("frappe.utils.pdf.get_pdf", return_value=b"%PDF-stub") as get_pdf:
			api.test_pdf(
				source="<p>BODY</p>",
				letter_head="claude-probe-letter-head",
				doctype="User",
				name="Administrator",
				context_prep="",
			)
		page = get_pdf.call_args.args[0]
		head, body, foot = page.index("HEAD Administrator"), page.index("<p>BODY</p>"), page.index("FOOT")
		self.assertLess(head, body)
		self.assertLess(body, foot)
		self.assertIn('class="letter-head"', page)
