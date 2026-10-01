"""What the document-reading prompts say for which site.

Site-less. Each prompt and schema is built from a `Locale`, so the cases are
two sites side by side: a company in Nepal keeping NPR with Bikram Sambat
switched on, and a company in the United States keeping USD without it. The
first is told about Bikram Sambat, PAN and VAT numbers and TDS; the second is
never offered "BS" as a calendar and hears nothing of Nepal. Both hear the
site's Additional Instructions, after everything else.
"""

import datetime
import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.api_integrations.claude import locale
from commons.banking import statement_import
from commons.document_capture import expense_claim, purchase_invoice

_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


NEPAL = locale.Locale(country="Nepal", currency="NPR", bikram_sambat=True)
USA = locale.Locale(country="United States", currency="USD", bikram_sambat=False)
OWN_WORDS = "Bills from Acme print the due date first."

# Words that belong to a Nepali site's prompt and to no other.
NEPALI = ("Bikram Sambat", '"BS"', "NPR", "PAN", "TDS", "Nepal", "2075")
# Phrasing that assumed whose documents these are.
SITE_SPECIFIC = ("our organisation", "our employees", "our expense types", "Thamel", "Bhojan")


def prompts(where: locale.Locale) -> dict[str, str]:
	"""Every document-reading prompt, as `where` would send it."""
	return {
		"invoice": purchase_invoice.instructions(where),
		"receipt": expense_claim.instructions(where),
		"statement": statement_import.document_instructions(where),
		"spreadsheet": statement_import.mapping_instructions(where),
	}


def calendars(where: locale.Locale) -> dict[str, list]:
	"""The `calendar` enum of every date in every schema, as `where` would send it."""
	invoice = purchase_invoice.schema(where)["properties"]
	receipt = expense_claim.schema(["Travel"], where)["properties"]["expenses"]["items"]["properties"]
	rows = statement_import.rows_schema(where)["properties"]["rows"]["items"]["properties"]
	return {
		"invoice_date": invoice["invoice_date"]["anyOf"][0]["properties"]["calendar"]["enum"],
		"due_date": invoice["due_date"]["anyOf"][0]["properties"]["calendar"]["enum"],
		"receipt": receipt["date"]["anyOf"][0]["properties"]["calendar"]["enum"],
		"statement_row": rows["date"]["properties"]["calendar"]["enum"],
		"spreadsheet": statement_import.mapping_schema(where)["properties"]["calendar"]["enum"],
	}


class TestBikramSambat(TestCase):
	def test_on_every_schema_offers_it(self):
		for field, enum in calendars(NEPAL).items():
			with self.subTest(field=field):
				self.assertEqual(enum, ["AD", "BS"])

	def test_off_no_schema_offers_it(self):
		for field, enum in calendars(USA).items():
			with self.subTest(field=field):
				self.assertEqual(enum, ["AD"])

	def test_on_every_prompt_explains_it_with_the_years_to_expect(self):
		for kind, text in prompts(NEPAL).items():
			with self.subTest(kind=kind):
				self.assertIn("Bikram Sambat (B.S. or वि.सं.)", text)
				self.assertIn('Mark those calendar "BS"', text)
				self.assertIn("do not convert them", text)

	def test_off_no_prompt_mentions_it(self):
		for kind, text in prompts(USA).items():
			with self.subTest(kind=kind):
				self.assertNotIn("Bikram", text)
				self.assertNotIn('"BS"', text)
				self.assertIn('calendar "AD"', text)

	def test_the_years_follow_the_calendar(self):
		"""2075 to 2090 in 2026, as the prompt has said; and on from there."""
		self.assertEqual(locale.bs_years(datetime.date(2026, 10, 1)), (2075, 2090))
		# Before mid-April the Bikram Sambat year is still the one before.
		self.assertEqual(locale.bs_years(datetime.date(2027, 3, 1)), (2075, 2090))
		self.assertEqual(locale.bs_years(datetime.date(2030, 5, 1)), (2079, 2094))
		self.assertIn("about 2075 to 2090", locale.date_rule(NEPAL, "invoices", datetime.date(2026, 10, 1)))

	def test_on_for_a_company_outside_nepal_says_only_that_some_use_it(self):
		elsewhere = locale.Locale(country="United States", currency="USD", bikram_sambat=True)
		rule = locale.date_rule(elsewhere, "invoices")
		self.assertIn("Some invoices are dated in Bikram Sambat", rule)
		self.assertIn("Invoices are often dated", locale.date_rule(NEPAL, "invoices"))


class TestTheCompany(TestCase):
	def test_nepal_hears_its_currency_tax_number_and_withholding_tax(self):
		invoice = purchase_invoice.instructions(NEPAL)
		self.assertIn("keeps its books in NPR (country: Nepal)", invoice)
		self.assertIn("give NPR", invoice)
		self.assertIn("tax_id is the PAN or VAT number (or other tax registration number)", invoice)
		self.assertIn("Leave out withholding tax (TDS)", invoice)
		party = purchase_invoice.schema(NEPAL)["properties"]["supplier"]["properties"]["tax_id"]
		self.assertIn("PAN or VAT number", party["description"])

	def test_a_us_company_hears_nothing_of_nepal(self):
		for kind, text in prompts(USA).items():
			with self.subTest(kind=kind):
				for word in NEPALI:
					self.assertNotIn(word, text)
		invoice = purchase_invoice.instructions(USA)
		self.assertIn("keeps its books in USD (country: United States)", invoice)
		self.assertIn("give USD", invoice)
		self.assertIn("tax_id is the tax registration number printed", invoice)
		self.assertIn("Leave out withholding tax:", invoice)
		party = purchase_invoice.schema(USA)["properties"]["buyer"]["properties"]["tax_id"]
		self.assertEqual(party["description"], "The tax registration number, as printed.")

	def test_a_company_with_no_currency_is_given_no_default(self):
		rule = locale.currency_rule(locale.Locale(), "invoice")
		self.assertIn("ISO 4217", rule)
		self.assertNotIn("keeps its books", rule)

	def test_no_prompt_says_whose_documents_these_are(self):
		for where in (NEPAL, USA):
			for kind, text in prompts(where).items():
				for phrase in SITE_SPECIFIC:
					with self.subTest(where=where.country, kind=kind, phrase=phrase):
						self.assertNotIn(phrase, text)


class TestAdditionalInstructions(TestCase):
	def test_every_prompt_ends_with_them(self):
		where = locale.Locale(country="Nepal", currency="NPR", additional_instructions=f"  {OWN_WORDS}\n")
		for kind, text in prompts(where).items():
			with self.subTest(kind=kind):
				self.assertTrue(text.rstrip().endswith(OWN_WORDS))
				self.assertIn("This site's own instructions", text)

	def test_none_adds_nothing(self):
		for kind, text in prompts(USA).items():
			with self.subTest(kind=kind):
				self.assertNotIn("This site's own instructions", text)

	def test_the_spreadsheet_rows_still_come_after_them(self):
		where = locale.Locale(additional_instructions=OWN_WORDS)
		answer = SimpleNamespace(
			stop_reason="end_turn", content=[SimpleNamespace(type="text", text='{"calendar": "AD"}')]
		)
		with patch.object(statement_import.claude, "create_message", return_value=answer) as sent:
			statement_import._read_mapping([["Date", "Amount"]], where)
		params = sent.call_args.kwargs
		content = params["messages"][0]["content"]
		self.assertLess(content.index(OWN_WORDS), content.index("<rows>"))
		self.assertEqual(
			params["output_config"]["format"]["schema"]["properties"]["calendar"]["enum"], ["AD"]
		)


class TestReadingUsesTheSitesLocale(TestCase):
	def test_an_invoice_is_read_for_the_readers_company(self):
		where = locale.Locale(country="United States", currency="USD", additional_instructions=OWN_WORDS)
		with (
			patch.object(purchase_invoice.locale, "for_company", return_value=where) as found,
			patch.object(purchase_invoice.documents, "read", return_value={}) as read,
		):
			purchase_invoice.read_scan(b"%PDF-1.7")
		found.assert_called_once_with()
		schema, instructions = read.call_args.args[1:3]
		self.assertEqual(
			schema["properties"]["invoice_date"]["anyOf"][0]["properties"]["calendar"]["enum"], ["AD"]
		)
		self.assertIn("give USD", instructions)
		self.assertIn(OWN_WORDS, instructions)

	def test_a_receipt_is_read_for_the_claimants_company(self):
		with (
			patch.object(expense_claim, "_claimant_company", return_value="Acme Inc"),
			patch.object(expense_claim.locale, "for_company", return_value=NEPAL) as found,
			patch.object(expense_claim.frappe, "get_all", return_value=["Travel"]),
			patch.object(expense_claim.documents, "read", return_value={}) as read,
		):
			expense_claim.read_scan(b"%PDF-1.7")
		found.assert_called_once_with("Acme Inc")
		schema, instructions = read.call_args.args[1:3]
		date = schema["properties"]["expenses"]["items"]["properties"]["date"]["anyOf"][0]
		self.assertEqual(date["properties"]["calendar"]["enum"], ["AD", "BS"])
		self.assertIn("Bikram Sambat", instructions)


class TestForCompany(TestCase):
	def locale_of(
		self, company=None, default="Example Org (Nepal)", companies=(), bs=True, extra="", terms=None
	):
		values = {
			"Example Org (Nepal)": {"country": "Nepal", "default_currency": "NPR"},
			"Example Org (USA)": {"country": "United States", "default_currency": "USD"},
		}
		with (
			patch.object(
				locale.frappe, "get_cached_value", lambda doctype, name, fields, as_dict: values.get(name)
			),
			patch.object(
				locale.frappe, "defaults", SimpleNamespace(get_user_default=lambda key: default), create=True
			),
			patch.object(locale.frappe, "db", SimpleNamespace(exists=lambda doctype, name: name in values)),
			patch.object(locale.frappe, "get_all", return_value=list(companies)),
			patch("commons.commons_core.settings.feature_enabled", return_value=bs),
			patch.object(locale.client, "additional_instructions", return_value=extra),
			patch.object(
				locale.client,
				"tax_terms",
				return_value=terms or {"tax_id_name": "", "withholding_tax_name": ""},
			),
		):
			return locale.for_company(company)

	def test_the_readers_default_company(self):
		self.assertEqual(self.locale_of(), locale.Locale(country="Nepal", currency="NPR", bikram_sambat=True))

	def test_a_named_company(self):
		found = self.locale_of("Example Org (USA)", bs=False, extra=OWN_WORDS)
		self.assertEqual(
			found,
			locale.Locale(
				country="United States",
				currency="USD",
				bikram_sambat=False,
				additional_instructions=OWN_WORDS,
			),
		)

	def test_the_only_company_when_there_is_no_default(self):
		found = self.locale_of(default=None, companies=["Example Org (USA)"])
		self.assertEqual(found.currency, "USD")

	def test_nothing_in_particular_when_there_is_no_telling(self):
		found = self.locale_of(default=None, companies=["A", "B"], bs=False)
		self.assertEqual(found, locale.Locale())

	def test_the_sites_tax_terms_come_from_claude_settings(self):
		found = self.locale_of(terms={"tax_id_name": "ABN", "withholding_tax_name": "PAYG"})
		self.assertEqual((found.tax_id_name, found.withholding_tax_name), ("ABN", "PAYG"))


class TestTheSitesTaxTerms(TestCase):
	"""Claude Settings' Tax ID Name and Withholding Tax Name, over `TAX_TERMS`."""

	def test_they_name_the_terms_where_the_country_has_none(self):
		where = locale.Locale(country="Australia", tax_id_name="ABN", withholding_tax_name="PAYG withholding")
		self.assertEqual(locale.tax_id_name(where), "ABN (or other tax registration number)")
		self.assertEqual(locale.withholding_name(where), "withholding tax (PAYG withholding)")
		invoice = purchase_invoice.instructions(where)
		self.assertIn("tax_id is the ABN (or other tax registration number)", invoice)
		party = purchase_invoice.schema(where)["properties"]["supplier"]["properties"]["tax_id"]
		self.assertIn("ABN", party["description"])

	def test_they_win_over_the_countrys(self):
		where = locale.Locale(country="Nepal", tax_id_name="  VAT number ", withholding_tax_name="")
		self.assertEqual(locale.tax_id_name(where), "VAT number (or other tax registration number)")
		# Only the one set is replaced; Nepal's withholding tax stays TDS.
		self.assertEqual(locale.withholding_name(where), "withholding tax (TDS)")

	def test_unset_they_change_nothing(self):
		self.assertEqual(locale.tax_id_name(USA), "tax registration number")
		self.assertEqual(locale.tax_id_name(NEPAL), "PAN or VAT number (or other tax registration number)")

	def test_claude_settings_has_the_fields(self):
		import json
		import os

		from commons.api_integrations.doctype import claude_settings

		path = os.path.join(os.path.dirname(claude_settings.__file__), "claude_settings.json")
		with open(path) as file:
			fields = {field["fieldname"]: field["fieldtype"] for field in json.load(file)["fields"]}
		self.assertEqual((fields["tax_id_name"], fields["withholding_tax_name"]), ("Data", "Data"))

	def test_the_client_reads_them_trimmed(self):
		document = SimpleNamespace(
			model="",
			get_password=lambda *args, **kwargs: "",
			get=lambda field: {"tax_id_name": " ABN ", "withholding_tax_name": None}.get(field),
		)
		with (
			patch.object(locale.client.frappe, "db", SimpleNamespace(exists=lambda *args, **kwargs: True)),
			patch.object(locale.client.frappe, "get_cached_doc", return_value=document),
		):
			self.assertEqual(locale.client.tax_terms(), {"tax_id_name": "ABN", "withholding_tax_name": ""})


class TestANewSupplier(TestCase):
	def test_is_left_to_erpnexts_default_supplier_type(self):
		made = {}

		def get_doc(values):
			made.update(values)
			return SimpleNamespace(insert=lambda: None, name=values["supplier_name"])

		with (
			patch.object(purchase_invoice.frappe, "db", SimpleNamespace(exists=lambda *args: False)),
			patch.object(purchase_invoice.frappe, "get_doc", get_doc),
		):
			self.assertEqual(purchase_invoice._new_supplier({"supplier_name": "Acme"}), "Acme")
		self.assertNotIn("supplier_type", made)
		self.assertEqual(made["doctype"], "Supplier")
