"""How a payroll accrual line is divided among employees, site-less.

What is pinned here is what would do damage quietly if it drifted: the parts
always add up to HRMS's line, a line whose parts do not is left as HRMS made
it, only Payable accounts get the employee as party, and the department comes
from the employee's salary slip.

That it gives the journal the "Split payroll accounts by party" server script
gave, with HRMS's totals, was checked against register.localhost inside a
rolled-back transaction: HR-PRUN-2026-00022's accrual rebuilt beside
ACC-JV-2026-00156.
"""

from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import payroll_lines as pl

# `flt` with a precision reads the site's rounding method; there is no site here.
_plain_flt = patch.object(
	pl, "flt", side_effect=lambda v, p=None: round(float(v or 0), p) if p is not None else float(v or 0)
)


def setUpModule():
	_plain_flt.start()


def tearDownModule():
	_plain_flt.stop()


class TestSplitTotal(TestCase):
	def test_the_parts_add_up_to_the_rounded_line(self):
		parts = pl.split_total({"E1": 1666.666666, "E2": 3333.333334}, 5000.0, 2)
		self.assertEqual(parts, {"E1": 1666.67, "E2": 3333.33})
		self.assertEqual(sum(parts.values()), 5000.0)

	def test_parts_that_do_not_add_up_are_refused(self):
		self.assertIsNone(pl.split_total({"E1": 100.0}, 150.0, 2))

	def test_no_parts_for_a_line_is_refused(self):
		self.assertIsNone(pl.split_total({}, 150.0, 2))


ACCOUNT_TYPES = {"TDS": "Payable", "Salary": None}


class Base:
	name = "PRUN-1"
	cost_center = "Main"

	def get_payable_amount_for_earnings_and_deductions(self, *args):
		raise AssertionError("HRMS's own lines were used")

	def get_accounting_entries_and_payable_amount(
		self,
		account,
		cost_center,
		amount,
		currencies,
		company_currency,
		payable_amount,
		accounting_dimensions,
		precision,
		entry_type="credit",
		party=None,
		accounts=None,
		**kw,
	):
		row = {"account": account, "amount": amount, "department": None}
		if party:
			row.update(party_type="Employee", party=party)
		accounts.append(row)
		return payable_amount + (amount if entry_type == "debit" else -amount)


class Run(pl.EmployeePayrollLinesMixin, Base):
	def __init__(self, parts):
		self._employee_parts = parts

	def _slip_departments(self):
		return {"E1": "Fellowship", "E2": "Facultyship"}


def post(run, earnings, deductions, dimensions=("department",)):
	accounts = []
	run.get_payable_amount_for_earnings_and_deductions(
		accounts, earnings, deductions, [], "NPR", list(dimensions), 2, 0, True
	)
	return accounts


@patch.object(pl, "feature_enabled", return_value=True)
@patch.object(pl.frappe, "get_cached_value", side_effect=lambda dt, name, field: ACCOUNT_TYPES.get(name))
class TestLines(TestCase):
	def test_one_line_per_employee_with_department_and_payable_party(self, *_):
		run = Run(
			{
				"earnings": {("Salary", "Main"): {"E1": 24000.0, "E2": 71000.0}},
				"deductions": {("TDS", "Main"): {"E1": 180.0, "E2": 5750.0}},
			}
		)
		accounts = post(run, {("Salary", "Main"): 95000.0}, {("TDS", "Main"): 5930.0})
		salary = [r for r in accounts if r["account"] == "Salary"]
		tds = [r for r in accounts if r["account"] == "TDS"]
		self.assertEqual(
			[(r["amount"], r["department"]) for r in salary],
			[(24000.0, "Fellowship"), (71000.0, "Facultyship")],
		)
		self.assertNotIn("party", salary[0])
		self.assertEqual(
			[(r["party"], r["department"]) for r in tds], [("E1", "Fellowship"), ("E2", "Facultyship")]
		)

	def test_a_line_that_does_not_split_stays_as_hrms_made_it(self, *_):
		run = Run({"earnings": {("Salary", "Main"): {"E1": 100.0}}, "deductions": {}})
		with patch.object(pl.frappe, "log_error") as logged:
			accounts = post(run, {("Salary", "Main"): 150.0}, {})
		self.assertEqual(accounts, [{"account": "Salary", "amount": 150.0, "department": None}])
		logged.assert_called_once()

	def test_no_department_dimension_no_department(self, *_):
		run = Run({"earnings": {("Salary", "Main"): {"E1": 100.0}}, "deductions": {}})
		accounts = post(run, {("Salary", "Main"): 100.0}, {}, dimensions=())
		self.assertIsNone(accounts[0]["department"])


class TestOff(TestCase):
	def test_off_leaves_hrmss_lines(self):
		with patch.object(pl, "feature_enabled", return_value=False):
			with self.assertRaisesRegex(AssertionError, "HRMS's own lines"):
				post(Run({}), {}, {})
