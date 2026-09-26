"""Who the scan page is for, and the rules that turn a scan into suggestions.

Site-less, like `banking.test_reconciliation`. What is pinned here is the part
that fails quietly: a supplier chosen for the reader that is not the one on the
invoice, an account guessed where the history had an answer, last invoice's
fixed tax amount copied onto this one, and a read billed to the site for
somebody who was never going to be allowed to save it.

That the draft inserts, and that ERPNext's totals come out right, was checked
against register.localhost's own invoices (see `purchase_invoice.py`), and is
not restated with mocks here.
"""

import logging
from types import SimpleNamespace
from typing import ClassVar
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.document_capture import purchase_invoice as capture

_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


def _raise(message, exc=ValueError, **kwargs):
	raise exc(message)


def row(**values):
	return frappe._dict(values)


class TestWhetherTheSiteHasIt(TestCase):
	def test_needs_erpnext_and_a_claude_key(self):
		for has_invoices, has_key, expected in (
			(True, True, True),
			(True, False, False),
			(False, True, False),
		):
			with (
				self.subTest(has_invoices=has_invoices, has_key=has_key),
				patch.object(capture.apps, "has_doctype", return_value=has_invoices),
				patch.object(capture.claude, "available", return_value=has_key),
			):
				self.assertEqual(capture.available(), expected)

	def test_is_for_whoever_may_create_a_purchase_invoice(self):
		with patch.object(capture.frappe, "has_permission", return_value=True) as asked:
			self.assertTrue(capture.can_capture())
		asked.assert_called_once_with("Purchase Invoice", "create")


@patch.object(capture.frappe, "throw", _raise)
class TestNothingIsReadForSomebodyWhoCannotSave(TestCase):
	"""Every read is billed, so the refusal has to come before the job is
	queued."""

	def request(self, content=b"%PDF-1.7"):
		return SimpleNamespace(files={"file": SimpleNamespace(stream=SimpleNamespace(read=lambda: content))})

	def test_no_permission_no_read(self):
		with (
			patch.object(capture, "available", return_value=True),
			patch.object(capture, "can_capture", return_value=False),
			patch.object(capture.READING, "start") as start,
		):
			with self.assertRaises(frappe.PermissionError):
				capture.start_reading()
		start.assert_not_called()

	def test_past_the_hourly_limit_no_read(self):
		cache = SimpleNamespace(
			make_key=lambda key: key,
			incrby=lambda key, by: capture.HOURLY_LIMIT + 1,
			expire=lambda key, seconds: None,
		)
		with (
			patch.object(capture, "_require"),
			patch.object(capture.frappe, "cache", cache, create=True),
			patch.object(capture.frappe, "request", self.request(), create=True),
			patch.object(capture.frappe, "session", SimpleNamespace(user="a@example.com"), create=True),
			patch.object(capture.READING, "start") as start,
		):
			with self.assertRaises(frappe.RateLimitExceededError):
				capture.start_reading()
		start.assert_not_called()

	def test_an_empty_file_is_refused_at_once_and_not_counted(self):
		with (
			patch.object(capture, "_require"),
			patch.object(capture.frappe, "request", self.request(b""), create=True),
			patch.object(capture, "_count_read") as counted,
			patch.object(capture.READING, "start") as start,
		):
			with self.assertRaisesRegex(ValueError, "empty"):
				capture.start_reading()
		counted.assert_not_called()
		start.assert_not_called()

	def test_a_readable_scan_is_handed_to_the_job(self):
		with (
			patch.object(capture, "_require"),
			patch.object(capture.frappe, "request", self.request(), create=True),
			patch.object(capture, "_count_read"),
			patch.object(capture.READING, "start", return_value="T") as start,
		):
			self.assertEqual(capture.start_reading(), {"token": "T"})
		start.assert_called_once_with(b"%PDF-1.7", step=None, lines=0)


@patch.object(capture.frappe, "throw", _raise)
class TestSavingAReadDraftNeedsNoKey(TestCase):
	"""A key removed or rotated after the scan was read must not strand the
	draft: `suggest`, `preview` and `create` never call Claude."""

	def setUp(self):
		self.enterContext(patch.object(capture.apps, "has_doctype", return_value=True))
		self.enterContext(patch.object(capture.claude, "available", return_value=False))

	def test_reading_still_needs_the_key(self):
		with patch.object(capture, "can_capture", return_value=True):
			with self.assertRaisesRegex(ValueError, "not set up"):
				capture._require()

	def test_preview_and_create_go_ahead_without_it(self):
		built = SimpleNamespace(
			name="PI-1",
			supplier="Vianet",
			currency="NPR",
			total=100,
			net_total=100,
			discount_amount=0,
			taxes=[],
			total_taxes_and_charges=0,
			grand_total=100,
			disable_rounded_total=1,
			rounded_total=100,
			insert=lambda: None,
		)
		with (
			patch.object(capture, "can_capture", return_value=True),
			patch.object(capture, "_build", return_value=built),
		):
			self.assertEqual(capture.preview({"company": "KC"})["grand_total"], 100)
			self.assertEqual(capture.create({"company": "KC"})["name"], "PI-1")

	def test_suggest_goes_ahead_without_it(self):
		with (
			patch.object(capture, "can_capture", return_value=True),
			patch.object(capture.frappe, "has_permission", return_value=True),
			patch.object(capture.frappe, "db", SimpleNamespace(get_value=lambda *args: None), create=True),
			patch.object(capture, "_history", return_value=[]),
			patch.object(capture, "_tax_options", return_value={}),
			patch.object(capture, "_duplicates", return_value=[]),
		):
			self.assertEqual(capture.suggest("KC", ["Tea"])["lines"][0]["review"], True)

	def test_the_permission_is_still_asked(self):
		with (
			patch.object(capture, "can_capture", return_value=False),
			patch.object(capture, "_build") as built,
		):
			for call in (
				lambda: capture.preview({}),
				lambda: capture.create({}),
				lambda: capture.suggest("KC", []),
			):
				with self.assertRaises(frappe.PermissionError):
					call()
		built.assert_not_called()


class TestReadingInTheBackground(TestCase):
	def test_reads_with_the_jobs_allowance_and_matches_what_it_read(self):
		extracted = {"buyer": {"name": "KC"}, "supplier": {"name": "Vianet"}}
		steps = []
		with (
			patch.object(capture.documents, "read", return_value=extracted) as read,
			patch.object(capture, "_companies", return_value=[]),
			patch.object(capture, "_match_company", return_value={"name": "KC", "reason": None}),
			patch.object(capture, "_match_suppliers", return_value=[]),
			patch.object(capture.claude, "model", return_value="claude-opus-5"),
		):
			result = capture.read_scan(b"%PDF-1.7", progress=lambda **changes: steps.append(changes))
		sent = read.call_args.kwargs
		self.assertEqual((sent["timeout"], sent["max_tokens"]), (capture.READ_TIMEOUT, capture.MAX_TOKENS))
		self.assertGreater(capture.MAX_TOKENS, 16000)
		self.assertIn("one invoice at a time", sent["too_long"])
		self.assertEqual(result["extracted"], extracted)
		self.assertEqual(result["company"]["name"], "KC")
		self.assertEqual(steps, [{"step": "reading"}, {"step": "matching"}])

	def test_the_job_may_run_as_long_as_the_read_and_more(self):
		self.assertGreater(capture.JOB_TIMEOUT, capture.READ_TIMEOUT)
		self.assertEqual(capture.READING.timeout, capture.JOB_TIMEOUT)
		self.assertEqual(capture.READING.method, f"{capture.__name__}.run_reading")


class TestSimilarity(TestCase):
	def test_spelling_of_the_suffix_does_not_matter(self):
		self.assertGreaterEqual(
			capture.similarity("VIANET COMMUNICATIONS PVT. LTD.", "Vianet Communications Pvt.Ltd"), 0.95
		)

	def test_a_letter_out_is_still_the_same_supplier(self):
		self.assertGreaterEqual(
			capture.similarity(
				"Arthabriksha Management Nepal P. Ltd", "Arthabrikshya Management Nepal Pvt Ltd"
			),
			capture.SUPPLIER_CHOSEN,
		)

	def test_one_long_word_in_common_is_not_a_match(self):
		self.assertLess(
			capture.similarity("Vianet Communications", "Worldlink Communications"), capture.SUPPLIER_OFFERED
		)

	def test_a_shortened_name_is_offered_but_not_chosen(self):
		score = capture.similarity("Vianet", "Vianet Communications Pvt.Ltd")
		self.assertGreaterEqual(score, capture.SUPPLIER_OFFERED)
		self.assertLess(score, capture.SUPPLIER_CHOSEN)

	def test_nothing_is_like_nothing(self):
		self.assertEqual(capture.similarity(None, "Vianet"), 0.0)
		self.assertEqual(capture.similarity("Pvt Ltd", "Pvt Ltd"), 0.0)


class TestWhichSupplier(TestCase):
	SUPPLIERS: ClassVar = [
		row(name="Vianet Communications Pvt.Ltd", supplier_name="Vianet Communications Pvt.Ltd", tax_id=None),
		row(name="Worldlink, Pvt Ltd", supplier_name="Worldlink Communications Pvt Ltd", tax_id=None),
		row(name="Muna Gurung", supplier_name="Muna Gurung", tax_id="108251384"),
	]

	def match(self, supplier):
		with patch.object(capture.frappe, "get_list", return_value=self.SUPPLIERS):
			return capture._match_suppliers(supplier)

	def test_the_tax_number_wins_whatever_the_name(self):
		found = self.match({"name": "M. Gurung Consulting", "tax_id": "108 251 384"})
		self.assertEqual(found[0]["name"], "Muna Gurung")
		self.assertTrue(found[0]["strong"])

	def test_the_same_name_is_chosen_and_nothing_else_is_offered(self):
		found = self.match({"name": "VIANET COMMUNICATIONS PVT. LTD.", "tax_id": None})
		self.assertEqual([match["name"] for match in found], ["Vianet Communications Pvt.Ltd"])
		self.assertTrue(found[0]["strong"])

	def test_a_stranger_is_nobody(self):
		self.assertEqual(self.match({"name": "Attic Restaurant", "tax_id": None}), [])

	def test_a_scan_with_no_supplier_does_not_look(self):
		with patch.object(capture.frappe, "get_list") as listed:
			self.assertEqual(capture._match_suppliers({"name": None, "tax_id": None}), [])
		listed.assert_not_called()


class TestWhichCompany(TestCase):
	COMPANIES: ClassVar = [
		row(name="Open Institute (Nepal)", company_name="Open Institute (Nepal)", tax_id=None),
		row(
			name="Kula Culture Management Training, Pvt. Ltd.",
			company_name="Kula Culture Management Training, Pvt. Ltd.",
			tax_id="605953985",
		),
	]

	def match(self, buyer, default=None):
		with patch.object(capture.frappe.defaults, "get_user_default", return_value=default):
			return capture._match_company(buyer, self.COMPANIES)

	def test_the_tax_number_first(self):
		found = self.match({"name": "Open Institute", "tax_id": "605-953-985"})
		self.assertEqual(found["name"], "Kula Culture Management Training, Pvt. Ltd.")

	def test_then_the_name(self):
		found = self.match({"name": "Open Institute Nepal", "tax_id": None})
		self.assertEqual(found["name"], "Open Institute (Nepal)")

	def test_then_the_readers_default_and_the_reason_says_it_is_a_guess(self):
		found = self.match({"name": None, "tax_id": None}, default="Open Institute (Nepal)")
		self.assertEqual(found["name"], "Open Institute (Nepal)")
		self.assertIn("default", found["reason"])

	def test_several_companies_and_no_clue_is_no_answer(self):
		self.assertIsNone(self.match({"name": None, "tax_id": None})["name"])


class TestWhichAccount(TestCase):
	HISTORY: ClassVar = [
		row(
			name="PI-3",
			supplier="Vianet",
			item_name="Internet from Vianet (6mo)",
			expense_account="Utility - KC",
		),
		row(name="PI-2", supplier="Vianet", item_name="Router", expense_account="Equipment - KC"),
		row(
			name="PI-1", supplier="Amatya", item_name="Statutory Audit 2080/81", expense_account="Legal - KC"
		),
	]

	def suggest(self, description, supplier):
		from_supplier = [line for line in self.HISTORY if line.supplier == supplier]
		return capture._suggest_account(description, from_supplier, self.HISTORY, "Cost of Goods Sold - KC")

	def test_like_this_suppliers_own_line_first(self):
		found = self.suggest("Internet from Vianet 6 months", "Vianet")
		self.assertEqual(found["account"], "Utility - KC")
		self.assertIn("PI-3", found["reason"])

	def test_then_where_this_supplier_usually_goes(self):
		found = self.suggest("Something new entirely", "Vianet")
		self.assertIn(found["account"], ("Utility - KC", "Equipment - KC"))
		self.assertIn("usually", found["reason"])
		self.assertFalse(found["review"])

	def test_then_a_line_described_the_same_way_from_anybody(self):
		found = self.suggest("Statutory Audit 2081/82", "A new auditor")
		self.assertEqual(found["account"], "Legal - KC")

	def test_last_the_default_and_it_asks_to_be_checked(self):
		found = self.suggest("Tea and biscuits", "A new cafe")
		self.assertEqual(found["account"], "Cost of Goods Sold - KC")
		self.assertTrue(found["review"])


def tax(**values):
	defaults = {
		"category": "Total",
		"add_deduct_tax": "Add",
		"charge_type": "On Net Total",
		"row_id": None,
		"account_head": "VAT - OI",
		"description": "VAT",
		"rate": 13,
		"cost_center": "Main - OI",
		"included_in_print_rate": 0,
		"tax_amount": 1300,
	}
	return row(**{**defaults, **values})


class TestCopyingLastInvoicesTaxes(TestCase):
	def test_rates_are_copied_and_amounts_are_not(self):
		rows = capture._rows_from_invoice(SimpleNamespace(taxes=[tax()]))
		self.assertEqual(rows[0]["rate"], 13)
		self.assertNotIn("tax_amount", rows[0])

	def test_a_fixed_amount_is_left_behind(self):
		invoice = SimpleNamespace(
			taxes=[tax(), tax(charge_type="Actual", description="TDS", add_deduct_tax="Deduct")]
		)
		self.assertEqual([line["description"] for line in capture._rows_from_invoice(invoice)], ["VAT"])

	def test_nothing_is_copied_if_that_would_break_a_row_reference(self):
		invoice = SimpleNamespace(
			taxes=[tax(charge_type="Actual"), tax(charge_type="On Previous Row Amount", row_id="1")]
		)
		self.assertEqual(capture._rows_from_invoice(invoice), [])


class TestTaxOptions(TestCase):
	def options(self, taxed, last=None, templates=()):
		with (
			patch.object(capture, "_last_taxed_invoice", return_value=last),
			patch.object(capture.frappe, "get_list", return_value=list(templates)),
			patch.object(capture, "_rows_from_template", return_value=[tax()]),
			patch.object(capture, "_rows_from_invoice", return_value=[tax()]),
		):
			return capture._tax_options("KC", "Vianet", taxed)

	def test_an_untaxed_scan_starts_untaxed(self):
		found = self.options(False, last=row(name="PI-3"), templates=[row(name="Nepal Tax", is_default=1)])
		self.assertEqual(found["suggested"], "none")

	def test_a_taxed_scan_follows_this_suppliers_last_invoice(self):
		found = self.options(True, last=row(name="PI-3"), templates=[row(name="Nepal Tax", is_default=1)])
		self.assertEqual(found["suggested"], "invoice:PI-3")

	def test_then_the_companys_default_template(self):
		found = self.options(
			True, templates=[row(name="Nepal Tax", is_default=1), row(name="Other", is_default=0)]
		)
		self.assertEqual(found["suggested"], "template:Nepal Tax")

	def test_several_templates_and_no_default_is_left_to_the_reader(self):
		found = self.options(True, templates=[row(name="A", is_default=0), row(name="B", is_default=0)])
		self.assertEqual(found["suggested"], "none")
		self.assertIn("Choose", found["reason"])

	def test_summary_does_not_say_the_rate_twice(self):
		self.assertEqual(capture._summarise([tax(description="VAT @ 13.0")]), "VAT @ 13.0")
		self.assertEqual(capture._summarise([tax(description="VAT")]), "VAT 13%")
		self.assertEqual(
			capture._summarise([tax(description="TDS", rate=15, add_deduct_tax="Deduct")]), "TDS \u221215%"
		)
