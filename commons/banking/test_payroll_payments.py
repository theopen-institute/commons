"""When an employee's payment may reference a payroll run, site-less.

What is pinned here is the gate: a Payroll Entry is a valid reference only for
an employee's payment, only with HRMS's employee-wise payroll accounting on
(the only thing that leaves salaries open per employee against the run), and
the references ERPNext checks itself still reach it without the run among them.

That a run's salaries are then paid, refused when overpaid and reopened on
cancel was checked against a site inside a rolled-back transaction: a payroll
run rebuilt from a past one, its accrual made, and its employees paid.
"""

from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from commons.banking import payroll_payments as pp


class Base:
	def __init__(self, party_type, references=()):
		self.party_type = party_type
		self.references = list(references)
		self.seen = None

	def get(self, field):
		return getattr(self, field)

	def get_valid_reference_doctypes(self):
		return ("Journal Entry",)

	def validate_reference_documents(self):
		self.seen = [d.reference_doctype for d in self.references]


class Payment(pp.PayrollPaymentEntryMixin, Base):
	pass


def reference(doctype, name="X-1", allocated=100):
	return frappe._dict(reference_doctype=doctype, reference_name=name, allocated_amount=allocated, idx=1)


class TestValidDoctypes(TestCase):
	@patch.object(pp, "payments_enabled", return_value=True)
	def test_an_employee_payment_may_reference_a_run(self, _):
		self.assertIn("Payroll Entry", Payment("Employee").get_valid_reference_doctypes())

	@patch.object(pp, "payments_enabled", return_value=True)
	def test_a_supplier_payment_may_not(self, _):
		self.assertNotIn("Payroll Entry", Payment("Supplier").get_valid_reference_doctypes())

	@patch.object(pp, "payments_enabled", return_value=False)
	def test_nor_anybody_with_the_feature_off(self, _):
		self.assertNotIn("Payroll Entry", Payment("Employee").get_valid_reference_doctypes())


class TestValidateReferences(TestCase):
	@patch.object(pp, "payments_enabled", return_value=True)
	def test_the_rest_are_checked_without_the_run_and_kept(self, _):
		refs = [reference("Journal Entry"), reference("Payroll Entry", "PRUN-1")]
		payment = Payment("Employee", refs)
		with patch.object(Payment, "_validate_run_reference") as checked:
			payment.validate_reference_documents()
		self.assertEqual(payment.seen, ["Journal Entry"])
		self.assertEqual(payment.references, refs)
		checked.assert_called_once()

	@patch.object(pp, "payments_enabled", return_value=False)
	@patch.object(pp, "_", side_effect=lambda text: text)
	@patch.object(pp.frappe, "throw", side_effect=frappe.ValidationError)
	def test_a_run_with_the_feature_off_is_refused(self, *_):
		payment = Payment("Employee", [reference("Payroll Entry", "PRUN-1")])
		with self.assertRaises(frappe.ValidationError):
			payment.validate_reference_documents()


class TestTheGate(TestCase):
	"""HRMS's Payroll Settings switch, not Commons Settings' payroll lines."""

	def test_on_when_hrms_accounts_per_employee(self):
		with (
			patch.object(pp.apps, "has_doctype", return_value=True),
			patch.object(pp.frappe, "db", MagicMock()) as db,
		):
			db.get_single_value.return_value = 1
			self.assertTrue(pp.payments_enabled())
		db.get_single_value.assert_called_with(
			"Payroll Settings", "process_payroll_accounting_entry_based_on_employee"
		)

	def test_off_otherwise_or_without_hrms(self):
		with (
			patch.object(pp.apps, "has_doctype", return_value=True),
			patch.object(pp.frappe, "db", MagicMock()) as db,
		):
			db.get_single_value.return_value = 0
			self.assertFalse(pp.payments_enabled())
		with patch.object(pp.apps, "has_doctype", return_value=False):
			self.assertFalse(pp.payments_enabled())
