"""Who a template's email goes to.

Site-less, like the settings tests: `recipients` only reads a doctype's meta and,
through a link, one record's address, and both are stubbed here.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.email_extensions import api


def meta(**fields):
	"""A doctype's meta holding `fieldname=(fieldtype, options)`."""
	docfields = {
		fieldname: SimpleNamespace(fieldname=fieldname, fieldtype=fieldtype, options=options)
		for fieldname, (fieldtype, options) in fields.items()
	}
	return SimpleNamespace(get_field=docfields.get)


class Record(dict):
	def __init__(self, doctype, **values):
		super().__init__(values)
		self.doctype = doctype


class TestRecipients(TestCase):
	def recipients(self, record, fieldnames, fields, linked=None):
		linked = linked or {}
		with (
			patch.object(api.frappe, "get_meta", return_value=meta(**fields)),
			patch.object(api, "address_of", side_effect=lambda dt, name: linked.get((dt, name), [])),
		):
			return api.recipients(record, fieldnames)

	def test_an_address_is_used_as_it_stands(self):
		record = Record("Fees", contact_email="a@example.org")
		self.assertEqual(
			self.recipients(record, "contact_email", {"contact_email": ("Data", "Email")}),
			["a@example.org"],
		)

	def test_a_dynamic_link_is_followed_to_the_record_it_names(self):
		# The Payment Entry the old scripts put `HR-EMP-00008` in the To box for.
		record = Record("Payment Entry", party_type="Employee", party="HR-EMP-00008")
		self.assertEqual(
			self.recipients(
				record,
				"party",
				{"party": ("Dynamic Link", "party_type"), "party_type": ("Link", "DocType")},
				linked={("Employee", "HR-EMP-00008"): ["t@example.org"]},
			),
			["t@example.org"],
		)

	def test_a_link_already_holding_an_address_is_not_followed(self):
		record = Record("Loan Repayment", applicant_type="Student", applicant="s@example.org")
		fields = {"applicant": ("Dynamic Link", "applicant_type")}
		with patch.object(api, "address_of") as address_of:
			with patch.object(api.frappe, "get_meta", return_value=meta(**fields)):
				self.assertEqual(api.recipients(record, "applicant"), ["s@example.org"])
		address_of.assert_not_called()

	def test_several_fields_in_order_without_repeats_and_empties_skipped(self):
		record = Record(
			"Student Applicant",
			student_email_id="a@example.org",
			guardian_email="",
			alt="a@example.org, b@example.org",
		)
		fields = {f: ("Data", "Email") for f in ("student_email_id", "guardian_email", "alt")}
		self.assertEqual(
			self.recipients(record, "student_email_id, guardian_email, missing, alt", fields),
			["a@example.org", "b@example.org"],
		)

	def test_a_plain_value_that_is_neither_address_nor_link_is_skipped(self):
		record = Record("Fees", student_name="Asha")
		self.assertEqual(self.recipients(record, "student_name", {"student_name": ("Data", None)}), [])

	def test_no_field_named_means_no_one(self):
		self.assertEqual(self.recipients(Record("Fees"), None, {}), [])


class TestAddressesIn(TestCase):
	def test_invalid_parts_are_dropped(self):
		self.assertEqual(api.addresses_in("a@example.org; not an address"), ["a@example.org"])

	def test_nothing_valid_is_empty(self):
		self.assertEqual(api.addresses_in("HR-EMP-00008"), [])


class TestMJML(TestCase):
	"""What a template's MJML compiles to. mrml runs for real; no site is needed."""

	def compile(self, body):
		from commons.email_extensions import mjml

		return mjml.to_html(f"<mjml><mj-body>{body}</mj-body></mjml>")[0]

	def section(self, text):
		return f"<mj-section><mj-column><mj-text>{text}</mj-text></mj-column></mj-section>"

	def test_jinja_that_is_not_xml_survives_the_compiler(self):
		html = self.compile(self.section('{% if total < 100 %}{{ "small" if a < b else "big" }}{% endif %}'))
		self.assertIn('{% if total < 100 %}{{ "small" if a < b else "big" }}{% endif %}', html)

	def test_a_loop_may_wrap_whole_sections(self):
		import jinja2

		html = self.compile("{% for row in rows %}" + self.section("{{ row }}") + "{% endfor %}")
		rendered = jinja2.Environment().from_string(html).render(rows=["first-row", "second-row"])
		self.assertIn("first-row", rendered)
		self.assertIn("second-row", rendered)

	def test_a_bare_ampersand_is_escaped_rather_than_refused(self):
		self.assertIn("Fees &amp; Charges", self.compile(self.section("Fees & Charges")))

	def test_an_entity_is_left_alone(self):
		self.assertIn("&nbsp;", self.compile(self.section("a&nbsp;b")))

	def test_the_doctype_is_one_premailer_keeps(self):
		# Every email goes through premailer, which drops MJML's lowercase one.
		self.assertTrue(self.compile(self.section("x")).startswith("<!DOCTYPE html>"))

	def test_the_layout_stays_responsive(self):
		self.assertIn("@media", self.compile(self.section("x")))

	def test_the_workflow_actions_marker_survives(self):
		self.assertIn("<!--workflow-actions-->", self.compile("<mj-raw><!--workflow-actions--></mj-raw>"))

	def test_what_does_not_parse_is_an_error(self):
		from commons.email_extensions import mjml

		with self.assertRaises(mjml.MJMLError):
			mjml.to_html("<mjml><mj-body><mj-section>")

	def test_jinja_an_editor_escaped_is_read_as_jinja(self):
		# GrapesJS writes `<` inside a Jinja tag back as `&lt;`.
		html = self.compile(self.section("{% if n &lt; 3 %}few{% endif %} {{ a &gt; b }}"))
		self.assertIn("{% if n < 3 %}few{% endif %}", html)
		self.assertIn("{{ a > b }}", html)


class TestOnceAcrossAmendments(TestCase):
	"""Whether a Notification already emailed about a version a document was amended from."""

	def sent_before(self, chain, emailed, amended_from="PE-1-1"):
		"""`chain` maps each version to the one it was amended from; `emailed` is the versions emailed about."""
		from types import SimpleNamespace

		from commons.email_extensions.notification import TemplateNotificationMixin

		database = SimpleNamespace(
			exists=lambda doctype, filters: filters["reference_name"] in emailed,
			get_value=lambda doctype, name, field: chain.get(name),
		)
		notification = SimpleNamespace(name="Payment Receipt")
		doc = SimpleNamespace(
			doctype="Payment Entry", get=lambda field: amended_from if field == "amended_from" else None
		)
		with patch("commons.email_extensions.notification.frappe.db", database):
			return TemplateNotificationMixin._sent_for_earlier_version(notification, doc)

	def test_an_original_emailed_about_is_not_emailed_about_again(self):
		self.assertTrue(self.sent_before({"PE-1-1": "PE-1"}, emailed={"PE-1"}))

	def test_an_original_whose_email_was_taken_back_is_emailed_about(self):
		# Taken back with its cancelled document, the Communication is gone.
		self.assertFalse(self.sent_before({"PE-1-1": "PE-1"}, emailed=set()))

	def test_the_whole_chain_of_corrections_is_followed(self):
		self.assertTrue(
			self.sent_before({"PE-1-2": "PE-1-1", "PE-1-1": "PE-1"}, emailed={"PE-1"}, amended_from="PE-1-1")
		)

	def test_a_document_amended_from_nothing_has_no_earlier_version(self):
		self.assertFalse(self.sent_before({}, emailed={"PE-1"}, amended_from=None))

	def test_a_chain_that_loops_ends(self):
		self.assertFalse(self.sent_before({"PE-1-1": "PE-1", "PE-1": "PE-1-1"}, emailed=set()))
