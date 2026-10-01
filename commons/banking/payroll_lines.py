"""A payroll accrual's earnings and deductions, one line per employee.

HRMS posts a payroll run's accrual journal with one line per account and cost
center: all of a run's Salary Expenses on one line, all its income tax on
another. With Payroll Settings' "Process Payroll Accounting Entry Based on
Employee" it splits the Payroll Payable line per employee too, but nothing
else. A site that reads its payroll by department (an accounting dimension on
Department) or keeps its withholding per employee (TDS
accounts of type Payable) needs every line split, and HRMS has no way to do
either: the dimension is copied from the Payroll Entry, one value for the whole
run, and the deduction lines carry no party.

Here each earnings and deduction total HRMS works out is split among the
employees it came from, from the same salary slip rows and the same cost center
percentages HRMS reads, and each line gets the employee's department from their
salary slip. A line on a Payable account also gets the employee as its party.
Lines that already name an employee -- Payroll Payable, advance recoveries --
get the department too.

HRMS's own arithmetic is left alone: its totals, advance deductions and
per-employee payable amounts are what they would have been. The split only
divides a total it has already made, and a total whose parts do not add back up
to it (HRMS has started reading the slips differently) keeps HRMS's own single
line, with an error logged, rather than being posted wrong.

Only the accrual journal is touched. Employer contributions, the bank entry and
any journal somebody makes against a payroll run are HRMS's own.
"""

from collections import defaultdict

import frappe
from frappe.utils import flt

from commons.commons_core.settings import ENABLE_PAYROLL_LINES, feature_enabled


def department_dimension(accounting_dimensions) -> str | None:
	"""The journal line field of the site's accounting dimension on Department,
	or None when it has none (or it is not among the run's `accounting_dimensions`).

	ERPNext has no built-in department dimension: `get_dimensions` adds only
	cost center and project to the ones a site defines. So it is the enabled
	Accounting Dimension whose Reference Document Type is Department, whatever
	its fieldname is.
	"""
	from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
		get_accounting_dimensions,
	)

	for dimension in get_accounting_dimensions(as_list=False):
		if dimension.document_type == "Department" and dimension.fieldname in accounting_dimensions:
			return dimension.fieldname
	return None


def split_total(parts: dict, total: float, precision: int) -> dict | None:
	"""`parts` ({employee: amount}) rounded so that they add up to `total`
	rounded, or None when they do not add up to it at all.

	The last employee takes the rounding remainder, the way HRMS's own employer
	contribution split does, so a line's parts always sum to the line.
	"""
	if abs(sum(parts.values()) - total) > 0.5 / 10**precision:
		return None
	rounded = {employee: flt(amount, precision) for employee, amount in parts.items()}
	if rounded:
		last = next(reversed(rounded))
		rounded[last] = flt(rounded[last] + flt(total, precision) - sum(rounded.values()), precision)
	return rounded


class EmployeePayrollLinesMixin:
	def get_salary_component_total(self, component_type=None, employee_wise_accounting_enabled=False):
		totals = super().get_salary_component_total(
			component_type=component_type,
			employee_wise_accounting_enabled=employee_wise_accounting_enabled,
		)
		if feature_enabled(ENABLE_PAYROLL_LINES):
			self._employee_parts = getattr(self, "_employee_parts", {})
			self._employee_parts[component_type] = self._parts_by_employee(component_type)
		return totals

	def _parts_by_employee(self, component_type: str) -> dict:
		"""{(account, cost_center): {employee: amount}}, as HRMS's totals are
		keyed, from the same rows and the same cost center split."""
		parts = defaultdict(lambda: defaultdict(float))
		for item in self.get_salary_components(component_type) or []:
			if self.get_advance_deduction(component_type, item):
				continue
			account = self.get_salary_component_account(item.salary_component)
			cost_centers = self.get_payroll_cost_centers_for_employee(item.employee, item.salary_structure)
			for cost_center, percentage in cost_centers.items():
				parts[(account, cost_center)][item.employee] += flt(item.amount) * percentage / 100
		return parts

	def get_payable_amount_for_earnings_and_deductions(
		self,
		accounts,
		earnings,
		deductions,
		currencies,
		company_currency,
		accounting_dimensions,
		precision,
		payable_amount,
		employee_wise_accounting_enabled,
	):
		if not feature_enabled(ENABLE_PAYROLL_LINES):
			return super().get_payable_amount_for_earnings_and_deductions(
				accounts,
				earnings,
				deductions,
				currencies,
				company_currency,
				accounting_dimensions,
				precision,
				payable_amount,
				employee_wise_accounting_enabled,
			)

		departments = self._slip_departments()
		department_field = department_dimension(accounting_dimensions)
		for component_type, totals, entry_type in (
			("earnings", earnings, "debit"),
			("deductions", deductions, "credit"),
		):
			employee_parts = getattr(self, "_employee_parts", {}).get(component_type, {})
			for (account, cost_center), total in totals.items():
				parts = split_total(employee_parts.get((account, cost_center), {}), total, precision)
				if parts is None:
					frappe.log_error(
						f"Payroll lines per employee: {account} did not split",
						f"{self.name}: the employees' parts of {account} ({cost_center}) do not add up "
						f"to HRMS's {total}, so it was posted as HRMS's single line.",
					)
					parts = {None: total}
				payable = frappe.get_cached_value("Account", account, "account_type") == "Payable"
				for employee, amount in parts.items():
					posted = len(accounts)
					payable_amount = self.get_accounting_entries_and_payable_amount(
						account,
						cost_center or self.cost_center,
						amount,
						currencies,
						company_currency,
						payable_amount,
						accounting_dimensions,
						precision,
						entry_type=entry_type,
						party=employee if payable else None,
						accounts=accounts,
					)
					if employee and len(accounts) > posted:
						self._set_department(accounts[-1], departments.get(employee), department_field)
		return payable_amount

	def set_payable_amount_against_payroll_payable_account(
		self,
		accounts,
		currencies,
		company_currency,
		accounting_dimensions,
		precision,
		payable_amount,
		payroll_payable_account,
		employee_wise_accounting_enabled,
	):
		super().set_payable_amount_against_payroll_payable_account(
			accounts,
			currencies,
			company_currency,
			accounting_dimensions,
			precision,
			payable_amount,
			payroll_payable_account,
			employee_wise_accounting_enabled,
		)
		if feature_enabled(ENABLE_PAYROLL_LINES):
			# Payroll Payable and advance recoveries: HRMS names the employee, not the department.
			departments = self._slip_departments()
			department_field = department_dimension(accounting_dimensions)
			for row in accounts:
				if row.get("party_type") == "Employee":
					self._set_department(row, departments.get(row.get("party")), department_field)

	def _slip_departments(self) -> dict:
		"""{employee: department} from this run's salary slips, as the accrual reads them."""
		slips = [d.name for d in self.get_sal_slip_list(ss_status=1, as_dict=True)]
		if not slips:
			return {}
		return dict(
			frappe.get_all(
				"Salary Slip",
				filters={"name": ["in", slips]},
				fields=["employee", "department"],
				as_list=True,
			)
		)

	@staticmethod
	def _set_department(row: dict, department: str | None, field: str | None) -> None:
		"""The slip's department on the line, in the department dimension's
		`field`, where the site has the dimension and the slip names one;
		otherwise whatever HRMS put there."""
		if department and field:
			row[field] = department
