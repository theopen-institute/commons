"""Reading a statement's rows once its layout is known.

Site-less. Claude's part (working out the layout, or copying rows off a PDF) is
not exercised here: what is pinned is the code that turns cells into amounts,
directions and dates, which is where a statement of a thousand rows is read
without a model and where a mistake would repeat on every row.
"""

import datetime
import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons.banking import statement_import as si

_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


class TestAmounts(TestCase):
	def test_reads_what_statements_print(self):
		cases = {
			"1,13,000.00": 113000.0,
			"2,500.00 Dr": 2500.0,
			"(500.00)": -500.0,
			"-75": -75.0,
			"75-": -75.0,
			"१२००": 1200.0,
			"NPR 5,000": 5000.0,
			12.5: 12.5,
		}
		for printed, expected in cases.items():
			with self.subTest(printed=printed):
				self.assertEqual(si.parse_amount(printed), expected)

	def test_blank_and_text_are_nothing(self):
		for printed in (None, "", "  ", "Balance", True, "1.2.3"):
			with self.subTest(printed=printed):
				self.assertIsNone(si.parse_amount(printed))

	def test_a_currency_beside_the_figure(self):
		"""The dot in "Rs." used to be read as a decimal point: dropped, or a hundredth."""
		cases = {
			"Rs. 1,000.00": 1000.0,
			"Rs.1500": 1500.0,
			"Rs -500": -500.0,
			"(Rs. 500)": -500.0,
			"₹ 2,50,000": 250000.0,
			"रु. १,२००": 1200.0,
			"5,000 NPR": 5000.0,
			"500.00 Cr": 500.0,
		}
		for printed, expected in cases.items():
			with self.subTest(printed=printed):
				self.assertEqual(si.parse_amount(printed), expected)

	def test_minus_signs_that_are_not_hyphens(self):
		for printed in ("−500", "–500", "500−"):
			with self.subTest(printed=printed):
				self.assertEqual(si.parse_amount(printed), -500.0)

	def test_the_decimal_separator_is_worked_out_not_assumed(self):
		cases = {
			"1.234,56": 1234.56,
			"1,234.56": 1234.56,
			"12,50": 12.5,
			"1,000": 1000.0,
			"1.234.567": 1234567.0,
			"1 234,56": 1234.56,
			"1'234.50": 1234.5,
		}
		for printed, expected in cases.items():
			with self.subTest(printed=printed):
				self.assertEqual(si.parse_amount(printed), expected)

	def test_what_cannot_be_read_without_guessing_is_nothing(self):
		for printed in ("1,2,3", "1.234.56", "1,23.456,7", "Page 2 of 3", "Balance 5", "05/07/2026", "12ab34"):
			with self.subTest(printed=printed):
				self.assertIsNone(si.parse_amount(printed))


class TestDates(TestCase):
	def test_excel_dates_are_taken_as_they_are(self):
		found = si.parse_date(datetime.datetime(2026, 7, 10))
		self.assertEqual((found["year"], found["month"], found["day"]), (2026, 7, 10))

	def test_text_dates_follow_the_banks_order(self):
		self.assertEqual(si.parse_date("03/04/2026", "DMY")["month"], 4)
		self.assertEqual(si.parse_date("03/04/2026", "MDY")["month"], 3)

	def test_a_four_digit_first_part_is_a_year_whatever_the_order(self):
		found = si.parse_date("2026-07-10", "DMY")
		self.assertEqual((found["year"], found["month"], found["day"]), (2026, 7, 10))

	def test_months_as_words(self):
		for printed in ("10 Jul 2026", "Jul 10, 2026", "10-JUL-26", "2026 July 10"):
			with self.subTest(printed=printed):
				found = si.parse_date(printed)
				self.assertEqual((found["year"], found["month"], found["day"]), (2026, 7, 10))

	def test_bikram_sambat_passes_through_unconverted(self):
		# A 32nd day exists in some BS months; the browser checks the calendar.
		found = si.parse_date("2083/03/32", "YMD")
		self.assertEqual((found["year"], found["month"], found["day"]), (2083, 3, 32))

	def test_footers_are_not_dates(self):
		for printed in ("Total", "Closing balance", "Page 2 of 3", None, "13/13/2026"):
			with self.subTest(printed=printed):
				self.assertIsNone(si.parse_date(printed))


GRID = [
	["Laxmi Sunrise Bank", None, None, None, None],
	["Account: 00111222333", None, None, None, None],
	["Date", "Narration", "Cheque", "Debit", "Credit", "Balance"],
	["01/07/2026", "Balance B/F", None, None, None, "100,000.00"],
	["05/07/2026", "FPQR-446377887", None, None, "5,000.00", "105,000.00"],
	["06/07/2026", "Cheque paid", "004512", "2,000.00", None, "103,000.00"],
	[None, "Total", None, "2,000.00", "5,000.00", None],
]

PAIRED = {
	"first_data_row": 3,
	"date_column": 0,
	"date_order": "DMY",
	"calendar": "AD",
	"description_columns": [1],
	"reference_column": 2,
	"withdrawal_column": 3,
	"deposit_column": 4,
	"amount_column": None,
	"amount_sign": None,
	"direction_column": None,
	"balance_column": 5,
}


class TestApplyingALayout(TestCase):
	def test_debit_and_credit_columns(self):
		rows = si.apply_mapping(GRID, PAIRED)
		# The brought-forward row has no amount, and the total no date.
		self.assertEqual([row["description"] for row in rows], ["FPQR-446377887", "Cheque paid"])
		self.assertEqual((rows[0]["deposit"], rows[0]["withdrawal"], rows[0]["balance"]), (5000.0, 0, 105000.0))
		self.assertEqual((rows[1]["withdrawal"], rows[1]["reference"]), (2000.0, "004512"))
		self.assertEqual(rows[0]["date"]["calendar"], "AD")

	def test_one_amount_column_with_dr_and_cr(self):
		grid = [
			["Date", "Details", "Amount", "Type"],
			["2026-07-05", "Receipt", "5000", "CR"],
			["2026-07-06", "Fee", "25", "DR"],
		]
		mapping = {**PAIRED, "first_data_row": 1, "description_columns": [1], "reference_column": None,
			"withdrawal_column": None, "deposit_column": None, "amount_column": 2, "direction_column": 3,
			"balance_column": None}
		rows = si.apply_mapping(grid, mapping)
		self.assertEqual([(r["deposit"], r["withdrawal"]) for r in rows], [(5000.0, 0), (0, 25.0)])

	def test_one_signed_amount_column(self):
		grid = [["05/07/2026", "Receipt", 5000], ["06/07/2026", "Fee", -25]]
		mapping = {**PAIRED, "first_data_row": 0, "reference_column": None, "withdrawal_column": None,
			"deposit_column": None, "amount_column": 2, "amount_sign": "negative_is_withdrawal",
			"balance_column": None}
		rows = si.apply_mapping(grid, mapping)
		self.assertEqual([(r["deposit"], r["withdrawal"]) for r in rows], [(5000.0, 0), (0, 25.0)])

	def test_direction_words_are_matched_whole(self):
		"""Anything starting with "d" used to be money out -- a "Deposit" included."""
		grid = [
			["05/07/2026", "Receipt", "5000", "Deposit"],
			["05/07/2026", "Receipt", "300", "DEP"],
			["06/07/2026", "Fee", "25", "Withdrawal"],
			["06/07/2026", "ATM", "40", "WDL"],
			["06/07/2026", "Card", "10", "Dr."],
			["06/07/2026", "Refund", "7", "C/R"],
		]
		mapping = {**PAIRED, "first_data_row": 0, "reference_column": None, "withdrawal_column": None,
			"deposit_column": None, "amount_column": 2, "direction_column": 3, "balance_column": None}
		rows = si.apply_mapping(grid, mapping)
		self.assertEqual(
			[(r["deposit"], r["withdrawal"]) for r in rows],
			[(5000.0, 0), (300.0, 0), (0, 25.0), (0, 40.0), (0, 10.0), (7.0, 0)],
		)

	def test_a_bare_d_is_a_deposit_beside_w_and_a_debit_beside_c(self):
		mapping = {**PAIRED, "first_data_row": 0, "reference_column": None, "withdrawal_column": None,
			"deposit_column": None, "amount_column": 2, "direction_column": 3, "balance_column": None}
		with_w = [["05/07/2026", "In", "100", "D"], ["06/07/2026", "Out", "20", "W"]]
		with_c = [["05/07/2026", "Out", "100", "D"], ["06/07/2026", "In", "20", "C"]]
		self.assertEqual([(r["deposit"], r["withdrawal"]) for r in si.apply_mapping(with_w, mapping)], [(100.0, 0), (0, 20.0)])
		self.assertEqual([(r["deposit"], r["withdrawal"]) for r in si.apply_mapping(with_c, mapping)], [(0, 100.0), (20.0, 0)])

	def test_rows_that_cannot_be_read_are_left_out_and_said_so(self):
		grid = [
			["Date", "Details", "Amount", "Type"],
			["05/07/2026", "Receipt", "5000", "CR"],
			["06/07/2026", "Garbled", "1.234.56", "DR"],
			["07/07/2026", "Odd", "25", "Reversal"],
			["08/07/2026", "Nil row", "-", "DR"],
		]
		mapping = {**PAIRED, "first_data_row": 1, "reference_column": None, "withdrawal_column": None,
			"deposit_column": None, "amount_column": 2, "direction_column": 3, "balance_column": None}
		notes = []
		rows = si.apply_mapping(grid, mapping, notes=notes)
		self.assertEqual([r["description"] for r in rows], ["Receipt"])
		self.assertEqual(len(notes), 2)
		self.assertIn("sheet rows 3", notes[0])
		self.assertIn("sheet rows 4", notes[1])

	def test_a_dash_in_a_paired_column_is_a_blank(self):
		grid = [["05/07/2026", "Receipt", "-", "5,000.00"], ["06/07/2026", "Fee", "Rs. 25", "—"]]
		mapping = {**PAIRED, "first_data_row": 0, "reference_column": None, "withdrawal_column": 2,
			"deposit_column": 3, "balance_column": None}
		notes = []
		rows = si.apply_mapping(grid, mapping, notes=notes)
		self.assertEqual([(r["deposit"], r["withdrawal"]) for r in rows], [(5000.0, 0), (0, 25.0)])
		self.assertEqual(notes, [])

	def test_a_dr_suffix_on_the_amount_itself(self):
		grid = [["05/07/2026", "Fee", "25.00 Dr"]]
		mapping = {**PAIRED, "first_data_row": 0, "reference_column": None, "withdrawal_column": None,
			"deposit_column": None, "amount_column": 2, "amount_sign": None, "balance_column": None}
		self.assertEqual(si.apply_mapping(grid, mapping)[0]["withdrawal"], 25.0)


class TestFileKinds(TestCase):
	def test_by_the_bytes(self):
		self.assertEqual(si.file_kind(b"%PDF-1.7 ..."), si.DOCUMENT)
		self.assertEqual(si.file_kind(b"PK\x03\x04rest"), si.XLSX)
		self.assertEqual(si.file_kind(b"\xd0\xcf\x11\xe0rest"), si.XLS)
		self.assertEqual(si.file_kind(b"Date,Narration,Amount\n05/07/2026,Fee,-25\n"), si.CSV)
		self.assertEqual(si.file_kind(b"\xff\xd8\xff\xe0 jpeg"), si.DOCUMENT)

	def test_a_csv_is_read_whatever_its_delimiter(self):
		grid = si.read_grid(b"Date;Narration;Amount\n05/07/2026;Fee;-25\n", si.CSV)
		self.assertEqual(grid[1], ["05/07/2026", "Fee", "-25"])

	def test_the_sample_names_every_column(self):
		self.assertEqual(si.sample([["Date", None, 5.0]]), "0. 0: Date | 2: 5")


class TestCountingRowsAsTheyStream(TestCase):
	def test_counts_each_row_once_even_when_a_key_is_split(self):
		reported = []
		counter = si.RowCounter(reported.append, interval=0)
		answer = '{"rows": [{"date": {}, "description": "a"}, {"date": {}, "description": "b"}], "notes": []}'
		# Fed in awkward pieces, one of which splits the key in two.
		pieces = [answer[i : i + 7] for i in range(0, len(answer), 7)]
		for piece in pieces:
			counter.feed(piece)
		self.assertEqual(counter.count, 2)
		self.assertEqual(reported, [1, 2])

	def test_reports_at_most_once_an_interval(self):
		reported = []
		counter = si.RowCounter(reported.append, interval=3600)
		counter.feed('"description" "description" ')
		counter.feed('"description"')
		self.assertEqual(counter.count, 3)
		self.assertEqual(reported, [2])


class TestTheBackgroundJob(TestCase):
	"""What the dialog is told, whichever way a reading ends."""

	def setUp(self):
		self.store = {}
		cache = SimpleNamespace(
			get_value=lambda key, expires=False: self.store.get(key),
			set_value=lambda key, value, expires_in_sec=None: self.store.__setitem__(key, value),
			delete_value=lambda key: self.store.pop(key, None),
			# Where `_()` looks for translations: none, rather than a logged error.
			hget=lambda *args, **kwargs: {},
		)
		self.enterContext(patch.object(si.frappe, "cache", cache))
		self.enterContext(patch.object(si.frappe, "session", SimpleNamespace(user="accounts@example.org")))
		self.enterContext(patch.object(si.frappe, "log_error"))
		self.store[si._state_key("T")] = {"status": "queued", "user": "accounts@example.org", "rows": 0}
		self.store[si._file_key("T")] = b"%PDF-1.7"

	def state(self):
		return self.store[si._state_key("T")]

	def test_a_finished_reading_carries_its_result_and_drops_the_file(self):
		with patch.object(si, "read_statement", return_value={"rows": [1, 2]}):
			si.run_reading("T")
		self.assertEqual(self.state()["status"], "done")
		self.assertEqual(self.state()["result"], {"rows": [1, 2]})
		self.assertNotIn(si._file_key("T"), self.store)

	def test_a_refusal_is_reported_in_its_own_words(self):
		import frappe

		with patch.object(si, "read_statement", side_effect=frappe.ValidationError("Claude declined to read this document.")):
			si.run_reading("T")
		self.assertEqual(self.state()["status"], "failed")
		self.assertEqual(self.state()["error"], "Claude declined to read this document.")

	def test_anything_else_is_logged_and_reported_plainly(self):
		with patch.object(si, "read_statement", side_effect=KeyError("rows")):
			si.run_reading("T")
		self.assertEqual(self.state()["error"], "Something went wrong reading the statement.")
		si.frappe.log_error.assert_called_once()

	def test_progress_reaches_the_state_while_reading(self):
		def read(content, progress):
			progress(status="reading", step="copying")
			progress(rows=12)
			self.assertEqual((self.state()["status"], self.state()["rows"]), ("reading", 12))
			return {"rows": []}

		with patch.object(si, "read_statement", side_effect=read):
			si.run_reading("T")

	def test_only_the_person_who_started_it_may_ask(self):
		self.assertEqual(si.reading_status("T")["status"], "queued")
		self.assertNotIn("user", si.reading_status("T"))
		with patch.object(si.frappe, "session", SimpleNamespace(user="someone@example.org")), patch.object(
			si.frappe, "throw", side_effect=ValueError
		):
			with self.assertRaises(ValueError):
				si.reading_status("T")

	def test_a_reading_the_worker_lost_is_reported_failed_not_left_reading(self):
		"""RQ killed the job at its timeout, or the worker died: nothing wrote
		`failed`, so the dialog would otherwise ask for an hour."""
		import time

		self.state().update(status="reading", queued_at=time.time() - 900, started_at=time.time() - 900)
		self.assertGreater(900, si.JOB_TIMEOUT)
		answer = si.reading_status("T")
		self.assertEqual(answer["status"], "failed")
		self.assertIn("stopped without an answer", answer["error"])

	def test_a_statement_too_long_for_one_answer_says_what_to_send(self):
		"""Not "one invoice at a time", which is what an invoice is told."""

		def throw(message, exc=None, **kwargs):
			raise ValueError(message)

		cut_off = SimpleNamespace(stop_reason="max_tokens", content=[])
		with (
			patch.object(si.documents.client, "stream_message", return_value=cut_off),
			patch.object(si.frappe, "throw", throw),
		):
			with self.assertRaisesRegex(ValueError, "fewer pages"):
				si.read_statement(b"%PDF-1.7")
