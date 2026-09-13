"""Arithmetic for the provisional procurement estimate.

Budget usage itself is not computed here: it is summed straight from submitted
Material Request rows in `budget.usage_rows`.
"""

from decimal import Decimal


def number(value):
	return Decimal(str(value or 0))


def outstanding_value(qty, covered_qty, rate):
	return max(number(qty) - number(covered_qty), Decimal(0)) * max(number(rate), Decimal(0))
