from unittest import TestCase

from tbs_commons.procurement.budget_math import number, outstanding_value


class TestBudgetMath(TestCase):
	def test_partial_coverage_reduces_provisional_value(self):
		self.assertEqual(outstanding_value(10, 4, 100), number(600))

	def test_full_or_excess_coverage_cannot_make_projection_negative(self):
		self.assertEqual(outstanding_value(10, 10, 100), number(0))
		self.assertEqual(outstanding_value(10, 25, 100), number(0))

	def test_negative_rate_cannot_credit_the_projection(self):
		self.assertEqual(outstanding_value(10, 0, -100), number(0))

	def test_values_are_exact_not_binary_floats(self):
		self.assertEqual(outstanding_value("0.1", 0, "0.2"), number("0.02"))
