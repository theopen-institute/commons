"""How an approval queue is grouped, and what the figure over a group means.

The grouping used to be the page's. The total printed beside each group is
money, so it is arrived at once, on the server; these pin what a group's
`estimate` is allowed to claim.
"""

from unittest import TestCase

import frappe

from commons.requests.procurement import group_by_department


def request(name, department, currency="GBP", cost=0):
	return frappe._dict(name=name, department=department, currency=currency, total_estimated_cost=cost)


class TestGroupByDepartment(TestCase):
	def test_one_department_is_one_group(self):
		groups = group_by_department([request("A", "Estates", cost=100), request("B", "Estates", cost=50)])
		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["requests"], ["A", "B"])
		self.assertEqual(groups[0]["estimate"], 150)

	def test_a_mixture_of_currencies_has_no_honest_total(self):
		groups = group_by_department(
			[
				request("A", "Estates", currency="GBP", cost=100),
				request("B", "Estates", currency="EUR", cost=50),
			]
		)
		self.assertIsNone(groups[0]["estimate"])

	def test_departments_are_ordered_by_name_so_acting_does_not_reshuffle_them(self):
		groups = group_by_department([request("A", "Works"), request("B", "Estates")])
		self.assertEqual([group["department"] for group in groups], ["Estates", "Works"])

	def test_a_request_without_a_department_sorts_last(self):
		groups = group_by_department([request("A", None), request("B", "Estates")])
		self.assertEqual([group["department"] for group in groups], ["Estates", None])
