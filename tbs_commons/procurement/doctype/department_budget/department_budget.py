import frappe
from frappe import _
from frappe.model.document import Document

from tbs_commons.procurement.budget import used_amount
from tbs_commons.procurement.budget_math import number

IDENTITY = ("company", "department", "fiscal_year")


class DepartmentBudget(Document):
	def validate(self):
		# Serialize allocation writes per department: the overlap check below is
		# only sound while no concurrent transaction can insert a rival period.
		frappe.db.sql("select name from `tabDepartment` where name=%s for update", self.department)
		year = frappe.get_doc("Fiscal Year", self.fiscal_year)
		if year.disabled or (year.companies and self.company not in [r.company for r in year.companies]):
			frappe.throw(_("Choose an active fiscal year belonging to this company."))
		department_company = frappe.db.get_value("Department", self.department, "company")
		if department_company and department_company != self.company:
			frappe.throw(_("Department and budget must belong to the same company."))
		self.currency = frappe.db.get_value("Company", self.company, "default_currency")
		self.start_date, self.end_date = year.year_start_date, year.year_end_date
		if number(self.annual_amount) < 0:
			frappe.throw(_("Annual budget cannot be negative."))
		self.validate_amendment()
		self.validate_single_active_period()
		self.validate_covers_usage()

	def validate_amendment(self):
		"""An amendment restates the amount, never the budget's identity."""
		if not self.amended_from:
			return
		previous = frappe.db.get_value(
			"Department Budget", self.amended_from, IDENTITY, as_dict=True
		)
		if previous and any(self.get(field) != previous.get(field) for field in IDENTITY):
			frappe.throw(
				_(
					"An amendment must keep the same company, department and fiscal year. Create a separate budget instead."
				)
			)

	def validate_single_active_period(self):
		"""Only one submitted allocation may cover a department at a given date."""
		if frappe.db.exists(
			"Department Budget",
			{
				"company": self.company,
				"department": self.department,
				"docstatus": 1,
				"name": ["!=", self.name],
				"start_date": ["<=", self.end_date],
				"end_date": [">=", self.start_date],
			},
		):
			frappe.throw(_("A submitted department budget already exists for this period."))

	def validate_covers_usage(self):
		"""A restated allocation cannot fall below what its period already carries.

		Usage is derived from department and date, so this reads the same figure
		whether the budget is new or an amendment: nothing has to be carried over.
		"""
		charged = used_amount(self)
		if number(self.annual_amount) < charged:
			frappe.throw(
				_(
					"The allocation cannot be less than the {0} already charged by submitted Material Requests."
				).format(f"{charged:,.2f}")
			)
