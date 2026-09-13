from unittest import TestCase

from tbs_commons.budget_math import number, totals


def row(kind, key, amount, qty, **links):
	return dict(kind=kind, row=key, amount=amount, qty=qty, **links)


class TestBudgetMath(TestCase):
	def setUp(self):
		self.request = row("request", "R", 10000, 10)
		self.order = row("order", "O", 9500, 10, request="R")

	def assertTotals(self, rows, reserved=0, committed=0, spent=0):
		self.assertEqual(
			totals(rows),
			{k: number(v) for k, v in dict(reserved=reserved, committed=committed, spent=spent).items()},
		)

	def test_approval_order_invoice_replace_previous_stage(self):
		self.assertTotals([self.request], reserved=10000)
		self.assertTotals([self.request, self.order], committed=9500)
		self.assertTotals(
			[self.request, self.order, row("invoice", "I", 9700, 10, order="O", request="R")], spent=9700
		)

	def test_partial_order_and_partial_invoice(self):
		order = row("order", "O", 3800, 4, request="R")
		invoice = row("invoice", "I", 2000, 2, order="O", request="R")
		self.assertTotals([self.request, order, invoice], reserved=6000, committed=1900, spent=2000)

	def test_two_orders_do_not_duplicate_reservation(self):
		self.assertTotals(
			[self.request, row("order", "A", 4000, 4, request="R"), row("order", "B", 5700, 6, request="R")],
			committed=9700,
		)

	def test_closed_order_restores_unfulfilled_request_reservation(self):
		self.order["closed"] = True
		self.assertTotals(
			[self.request, self.order, row("invoice", "I", 1900, 2, order="O", request="R")],
			reserved=8000,
			spent=1900,
		)

	def test_direct_invoice_consumes_request_reservation(self):
		self.assertTotals(
			[self.request, row("invoice", "I", 3000, 3, request="R")], reserved=7000, spent=3000
		)

	def test_direct_purchases_and_credit_notes(self):
		self.assertTotals([row("invoice", "I", 1000, 2), row("invoice", "C", -500, -1)], spent=500)

	def test_return_restores_order_commitment(self):
		self.assertTotals(
			[
				self.request,
				self.order,
				row("invoice", "I", 9500, 10, order="O"),
				row("invoice", "C", -950, -1, order="O"),
			],
			committed=950,
			spent=8550,
		)

	def test_extra_order_quantity_never_creates_negative_reservation(self):
		self.assertTotals([self.request, row("order", "O", 12000, 12, request="R")], committed=12000)

	def test_cancellation_releases_or_restores_correct_stage(self):
		invoice = row("invoice", "I", 9500, 10, order="O")
		self.assertTotals([self.request, self.order, invoice], spent=9500)
		self.assertTotals([self.request, self.order], committed=9500)
		self.assertTotals([self.request], reserved=10000)
		self.assertTotals([])
