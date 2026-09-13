import frappe
from frappe import _
from frappe.model.document import Document

from tbs_commons.procurement.budget_math import number, totals


class DepartmentBudget(Document):
	def validate(self):
		from tbs_commons.procurement.budget import (
			lock_budget,
			portfolio,
			positions,
			validate_reconciled_material_requests,
		)

		frappe.db.sql("select name from `tabDepartment` where name=%s for update", self.department)
		year = frappe.get_doc("Fiscal Year", self.fiscal_year)
		if year.disabled or (year.companies and self.company not in [r.company for r in year.companies]):
			frappe.throw(_("Choose an active fiscal year belonging to this company."))
		department_company = frappe.db.get_value("Department", self.department, "company")
		if department_company and department_company != self.company:
			frappe.throw(_("Department and budget must belong to the same company."))
		self.currency = frappe.db.get_value("Company", self.company, "default_currency")
		self.start_date, self.end_date = year.year_start_date, year.year_end_date
		self.budget_key = f"{self.company}|{self.department}|{self.fiscal_year}"
		if number(self.annual_amount) < 0:
			frappe.throw(_("Annual budget cannot be negative."))
		old = self.get_doc_before_save()
		if not self.is_new():
			lock_budget(self.name)
			if old:
				for field in ("company", "department", "fiscal_year", "annual_amount"):
					if self.get(field) != old.get(field):
						frappe.throw(
							_("Keep the original allocation unchanged; append a budget adjustment instead.")
						)
				for idx, row in enumerate(old.adjustments):
					if idx >= len(self.adjustments) or any(
						self.adjustments[idx].get(f) != row.get(f) for f in ("name", "amount", "reason")
					):
						frappe.throw(
							_(
								"Existing budget adjustments cannot be changed or removed. Append a reversing adjustment."
							)
						)
		amount = number(self.annual_amount) + sum((number(r.amount) for r in self.adjustments), number(0))
		used = (
			sum(totals(portfolio(positions(self.name, lock=not self.is_new()))).values())
			if not self.is_new()
			else 0
		)
		if amount < used or amount < 0:
			frappe.throw(_("The revised budget cannot be less than submitted Material Request usage."))
		if frappe.db.exists(
			"Department Budget",
			{
				"company": self.company,
				"department": self.department,
				"name": ["!=", self.name],
				"start_date": ["<=", self.end_date],
				"end_date": [">=", self.start_date],
			},
		):
			frappe.throw(_("A department budget already exists for this period."))
		if self.ready:
			validate_reconciled_material_requests(self)
