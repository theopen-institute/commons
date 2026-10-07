"""Paying a payroll run's salaries with one Payment Entry per employee.

With Payroll Settings' "Process Payroll Accounting Entry Based on Employee",
HRMS credits each employee's net pay to Payroll Payable on the run's accrual
journal, with the employee as party and the Payroll Entry as reference. That
reference is what the payment ledger keys the salary on: what an employee is
owed for a run is open against the Payroll Entry, not against the journal.

HRMS pays that with its own "Make Bank Entry", one Journal Entry for the whole
run. A site that pays each employee by their own bank transfer wants a Payment
Entry each, and ERPNext will not let one settle the salary. An employee's
payment may reference a Journal Entry only through a line with no reference of
its own ("does not have account ... or already matched against another
voucher"), and may not reference a Payroll Entry at all.

So here an employee's Payment Entry may reference a Payroll Entry, and ERPNext
then does what it does for a Journal Entry: the reference's outstanding is
what the payment ledger still has open against the run for that employee, and
the payment's ledger rows are posted against the run, where the salary is. The
party check ERPNext makes on other references (the document's `employee`) is
made against the ledger instead: the run must owe the employee something in the
payment's party account.

The Payroll Entry form gets a "Create Payment Entries" button, once the run's
accrual is submitted and as long as somebody on it is unpaid. It makes draft
Payment Entries for the employees picked, each for what the run still owes them.

All of it rides on HRMS's own Payroll Settings switch, because that is the
only thing that leaves a run's salaries open per employee against the Payroll
Entry. Commons Settings' "Enable Payroll Lines per Employee"
(`commons.banking.payroll_lines`) does not: it splits the earnings and
deduction lines, and names the employee only on Payable accounts such as TDS,
without a reference to the run; the Payroll Payable line it leaves to HRMS. So
with HRMS's switch off, an employee's payment cannot reference a Payroll Entry
and the button does not appear, whatever Commons Settings says. A run accrued
while it was on and paid after it was turned off is paid from the desk.

What the dialog starts on, a Mode of Payment and a Reference No, is Commons
Settings' "Payroll Payment Mode of Payment" and "Payroll Payment Reference",
blank for none.
"""

import frappe
from frappe import _
from frappe.query_builder.functions import Sum
from frappe.utils import flt, getdate, nowdate

from commons.commons_core import apps
from commons.commons_core.settings import (
	PAYROLL_PAYMENT_MODE_OF_PAYMENT,
	PAYROLL_PAYMENT_REFERENCE,
)
from commons.commons_core.settings import value as setting

PAYROLL_ENTRY = "Payroll Entry"
PAYROLL_SETTINGS = "Payroll Settings"
# HRMS's "Process Payroll Accounting Entry Based on Employee".
EMPLOYEE_WISE_ACCOUNTING = "process_payroll_accounting_entry_based_on_employee"


def payments_enabled() -> bool:
	"""Whether HRMS posts each employee's net pay to Payroll Payable against the
	run, with the employee as party -- the ledger rows `owed_by_run` reads."""
	return bool(
		apps.has_doctype(PAYROLL_SETTINGS)
		and frappe.db.get_single_value(PAYROLL_SETTINGS, EMPLOYEE_WISE_ACCOUNTING)
	)


def owed_by_run(payroll_entry: str, account: str, employee: str | None = None) -> dict:
	"""{employee: (outstanding, total)} still open in `account` against the run.

	Outstanding is what the payment ledger has open against the run for the
	employee, positive while the run owes them; total is what the run's own
	vouchers credited them, before any payment.
	"""
	ple = frappe.qb.DocType("Payment Ledger Entry")
	query = (
		frappe.qb.from_(ple)
		.select(ple.party, ple.voucher_type, Sum(ple.amount_in_account_currency).as_("amount"))
		.where(
			(ple.against_voucher_type == PAYROLL_ENTRY)
			& (ple.against_voucher_no == payroll_entry)
			& (ple.account == account)
			& (ple.party_type == "Employee")
			& (ple.delinked == 0)
		)
		.groupby(ple.party, ple.voucher_type)
	)
	if employee:
		query = query.where(ple.party == employee)

	owed = {}
	for row in query.run(as_dict=True):
		outstanding, total = owed.get(row.party, (0.0, 0.0))
		outstanding += flt(row.amount)
		if row.voucher_type == "Journal Entry" and flt(row.amount) > 0:
			total += flt(row.amount)
		owed[row.party] = (outstanding, total)
	return owed


class PayrollPaymentEntryMixin:
	def get_valid_reference_doctypes(self):
		doctypes = super().get_valid_reference_doctypes()
		if self.party_type == "Employee" and doctypes and payments_enabled():
			doctypes = (*doctypes, PAYROLL_ENTRY)
		return doctypes

	def _run_references(self) -> list:
		return [
			d for d in self.get("references") if d.reference_doctype == PAYROLL_ENTRY and d.reference_name
		]

	def set_missing_ref_details(
		self,
		force: bool = False,
		update_ref_details_only_for: list | None = None,
		reference_exchange_details: dict | None = None,
	) -> None:
		super().set_missing_ref_details(
			force=force,
			update_ref_details_only_for=update_ref_details_only_for,
			reference_exchange_details=reference_exchange_details,
		)
		# ERPNext reads a Payroll Entry as an order, and finds no total on it.
		for d in self._run_references():
			if not d.allocated_amount or self.party_type != "Employee":
				continue
			if (
				update_ref_details_only_for
				and (d.reference_doctype, d.reference_name) not in update_ref_details_only_for
			):
				continue
			outstanding, total = owed_by_run(d.reference_name, self.party_account, self.party).get(
				self.party, (0.0, 0.0)
			)
			for field, value in (
				("outstanding_amount", outstanding),
				("total_amount", total),
				("exchange_rate", 1),
			):
				if self.get("_action") in ("submit", "cancel"):
					d.db_set(field, value)
				else:
					d.set(field, value)

	def validate_reference_documents(self):
		runs = self._run_references()
		if not runs:
			return super().validate_reference_documents()

		# ERPNext would look for the run's `employee`; it has none.
		references = self.references
		self.references = [d for d in references if d not in runs]
		try:
			super().validate_reference_documents()
		finally:
			self.references = references

		valid_doctypes = self.get_valid_reference_doctypes() or ()
		for d in runs:
			if d.allocated_amount:
				self._validate_run_reference(d, valid_doctypes)

	def _validate_run_reference(self, d, valid_doctypes) -> None:
		if PAYROLL_ENTRY not in valid_doctypes:
			frappe.throw(
				_("Row #{0}: a {1} can only be paid here by an employee's payment, with {2} on.").format(
					d.idx,
					_(PAYROLL_ENTRY),
					_("Payroll Settings: Process Payroll Accounting Entry Based on Employee"),
				)
			)
		run = frappe.db.get_value(
			PAYROLL_ENTRY, d.reference_name, ["docstatus", "company", "payroll_payable_account"], as_dict=True
		)
		if not run:
			frappe.throw(_("{0} {1} does not exist").format(_(PAYROLL_ENTRY), d.reference_name))
		if run.docstatus != 1:
			frappe.throw(_("{0} {1} must be submitted").format(_(PAYROLL_ENTRY), d.reference_name))
		if run.company != self.company:
			frappe.throw(
				_("Row #{0}: {1} belongs to {2}, not {3}").format(
					d.idx, d.reference_name, run.company, self.company
				)
			)
		if run.payroll_payable_account != self.party_account:
			frappe.throw(
				_("Row #{0}: {1} owes its salaries in {2}, but Party Account is {3}").format(
					d.idx, d.reference_name, run.payroll_payable_account, self.party_account
				)
			)
		if d.reference_name and not owed_by_run(d.reference_name, self.party_account, self.party):
			frappe.throw(
				_("Row #{0}: {1} has no salary for {2} in {3}").format(
					d.idx, d.reference_name, self.party, self.party_account
				)
			)


def _run_for_payments(payroll_entry: str):
	run = frappe.get_doc(PAYROLL_ENTRY, payroll_entry)
	run.check_permission("read")
	return run


def _draft_payments(run) -> dict:
	"""{employee: draft Payment Entry} already referencing the run."""
	pe = frappe.qb.DocType("Payment Entry")
	ref = frappe.qb.DocType("Payment Entry Reference")
	rows = (
		frappe.qb.from_(pe)
		.join(ref)
		.on(ref.parent == pe.name)
		.select(pe.party, pe.name)
		.where(
			(pe.docstatus == 0)
			& (pe.party_type == "Employee")
			& (ref.reference_doctype == PAYROLL_ENTRY)
			& (ref.reference_name == run.name)
		)
	).run(as_dict=True)
	return {r.party: r.name for r in rows}


@frappe.whitelist()
def get_unpaid_salaries(payroll_entry: str) -> dict:
	"""Who the run still owes, and the defaults the payment dialog starts from.

	Empty `employees` -- the button stays hidden -- until the run's accrual is
	submitted, once everybody is paid, and while HRMS's employee-wise payroll
	accounting is off.
	"""
	run = _run_for_payments(payroll_entry)
	if run.docstatus != 1 or not payments_enabled():
		return {"employees": []}

	owed = owed_by_run(run.name, run.payroll_payable_account)
	drafts = _draft_payments(run)
	names = dict(
		frappe.get_all(
			"Employee",
			filters={"name": ["in", list(owed) or [""]]},
			fields=["name", "employee_name"],
			as_list=True,
		)
	)
	precision = frappe.get_precision("Payment Entry", "paid_amount")
	employees = [
		{
			"employee": employee,
			"employee_name": names.get(employee),
			"amount": flt(outstanding, precision),
			"draft": drafts.get(employee),
		}
		for employee, (outstanding, _total) in sorted(owed.items())
		if flt(outstanding, precision) > 0
	]

	mode_of_payment = setting(PAYROLL_PAYMENT_MODE_OF_PAYMENT)
	if mode_of_payment and not frappe.db.exists("Mode of Payment", mode_of_payment):
		mode_of_payment = None
	paid_from = run.payment_account or (
		mode_of_payment
		and frappe.db.get_value(
			"Mode of Payment Account", {"parent": mode_of_payment, "company": run.company}, "default_account"
		)
	)
	return {
		"employees": employees,
		"company": run.company,
		"mode_of_payment": mode_of_payment,
		"paid_from": paid_from,
		"reference_no": setting(PAYROLL_PAYMENT_REFERENCE),
	}


@frappe.whitelist(methods=["POST"])
def make_salary_payments(
	payroll_entry: str,
	employees: list | str,
	posting_date: str,
	paid_from: str,
	mode_of_payment: str | None = None,
	reference_no: str | None = None,
) -> list[str]:
	"""A draft Payment Entry for each of `employees`, for what the run still owes them."""
	employees = frappe.parse_json(employees) if isinstance(employees, str) else employees
	run = _run_for_payments(payroll_entry)
	if run.docstatus != 1:
		frappe.throw(_("Submit {0} first.").format(run.name))
	frappe.has_permission("Payment Entry", "create", throw=True)

	owed = owed_by_run(run.name, run.payroll_payable_account)
	drafts = _draft_payments(run)
	precision = frappe.get_precision("Payment Entry", "paid_amount")
	created = []
	for employee in employees:
		amount = flt(owed.get(employee, (0.0, 0.0))[0], precision)
		if amount <= 0:
			frappe.throw(_("{0} owes {1} nothing.").format(run.name, employee))
		if drafts.get(employee):
			frappe.throw(_("{0} already has a draft payment, {1}.").format(employee, drafts[employee]))

		payment = frappe.get_doc(
			{
				"doctype": "Payment Entry",
				"payment_type": "Pay",
				"company": run.company,
				"posting_date": getdate(posting_date or nowdate()),
				"mode_of_payment": mode_of_payment,
				"party_type": "Employee",
				"party": employee,
				"paid_from": paid_from,
				"paid_to": run.payroll_payable_account,
				"paid_amount": amount,
				"received_amount": amount,
				"source_exchange_rate": 1,
				"target_exchange_rate": 1,
				"reference_no": reference_no,
				"reference_date": getdate(posting_date or nowdate()),
				"bank_account": run.bank_account,
				"party_bank_account": frappe.db.get_value(
					"Bank Account", {"party_type": "Employee", "party": employee, "is_default": 1}, "name"
				),
				"cost_center": run.cost_center,
				"references": [
					{
						"reference_doctype": PAYROLL_ENTRY,
						"reference_name": run.name,
						"allocated_amount": amount,
					}
				],
			}
		)
		payment.insert()
		created.append(payment.name)
	return created
