from unittest import TestCase

from tbs_commons.budget_math import number, outstanding_value, totals


class TestBudgetMath(TestCase):
	def test_only_material_requests_contribute_to_usage(self):
		rows = [{"kind": kind, "amount": 100} for kind in ("request", "order", "invoice", "material_request")]
		self.assertEqual(totals(rows), {"used": number(100)})

	def test_purchase_and_issue_values_add(self):
		self.assertEqual(
			totals(
				[
					{"kind": "material_request", "type": "Purchase", "amount": "125.50"},
					{"kind": "material_request", "type": "Material Issue", "amount": "75.25"},
				]
			),
			{"used": number("200.75")},
		)

	def test_partial_coverage_reduces_provisional_value(self):
		self.assertEqual(outstanding_value(10, 4, 100), number(600))

	def test_full_or_excess_coverage_cannot_make_projection_negative(self):
		self.assertEqual(outstanding_value(10, 10, 100), 0)
		self.assertEqual(outstanding_value(10, 12, 100), 0)

	def test_cancelled_positions_do_not_contribute(self):
		self.assertEqual(totals([]), {"used": 0})

	def test_negative_estimates_cannot_increase_projected_availability(self):
		self.assertEqual(outstanding_value(10, 0, -100), 0)
