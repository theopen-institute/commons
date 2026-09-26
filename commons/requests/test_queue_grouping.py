"""How an approval queue is grouped, and what the figure over a group means.

The grouping used to be the page's, which was harmless, and so was the total
printed beside it -- until that total ended up next to the allocation it is
weighed against. Two figures that are read together should not be arrived at in
two places, so both are the server's now. These pin what the group's `estimate`
is allowed to claim.
"""

from unittest import TestCase

import frappe

from commons.requests.procurement import group_by_department


def request(name, department, budget=None, currency="GBP", cost=0):
	return frappe._dict(
		name=name,
		department=department,
		currency=currency,
		total_estimated_cost=cost,
		budget_summary={"name": budget, "department": department} if budget else None,
	)


class TestGroupByDepartment(TestCase):
	def test_requests_charged_to_one_allocation_are_one_group(self):
		groups = group_by_department(
			[
				request("A", "Estates", budget="B-1", cost=100),
				request("B", "Estates", budget="B-1", cost=50),
			]
		)
		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["requests"], ["A", "B"])
		self.assertEqual(groups[0]["estimate"], 150)

	def test_one_department_straddling_two_budget_periods_is_two_groups(self):
		"""A readout belongs to a period, and cannot speak for the other one."""
		groups = group_by_department(
			[
				request("A", "Estates", budget="B-2025", cost=100),
				request("B", "Estates", budget="B-2026", cost=50),
			]
		)
		self.assertEqual([group["estimate"] for group in groups], [100, 50])

	def test_a_mixture_of_currencies_has_no_honest_total(self):
		groups = group_by_department(
			[
				request("A", "Estates", budget="B-1", currency="GBP", cost=100),
				request("B", "Estates", budget="B-1", currency="EUR", cost=50),
			]
		)
		self.assertIsNone(groups[0]["estimate"])

	def test_departments_are_ordered_by_name_so_acting_does_not_reshuffle_them(self):
		groups = group_by_department(
			[
				request("A", "Works", budget="B-2"),
				request("B", "Estates", budget="B-1"),
			]
		)
		self.assertEqual([group["department"] for group in groups], ["Estates", "Works"])

	def test_a_request_without_a_department_sorts_last(self):
		groups = group_by_department([request("A", None), request("B", "Estates", budget="B-1")])
		self.assertEqual([group["department"] for group in groups], ["Estates", None])

	def test_the_department_falls_back_to_the_one_the_budget_names(self):
		row = request("A", None, budget="B-1")
		row.budget_summary["department"] = "Estates"
		self.assertEqual(group_by_department([row])[0]["department"], "Estates")
