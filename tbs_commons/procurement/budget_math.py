"""Material Requests are the only posted departmental budget usage."""

from decimal import Decimal


def number(value):
	return Decimal(str(value or 0))


def totals(rows):
	# Older request/order/invoice snapshots are audit history, not this tally.
	return {
		"used": sum((number(row["amount"]) for row in rows if row["kind"] == "material_request"), Decimal(0))
	}


def outstanding_value(qty, covered_qty, rate):
	return max(number(qty) - number(covered_qty), Decimal(0)) * max(number(rate), Decimal(0))
