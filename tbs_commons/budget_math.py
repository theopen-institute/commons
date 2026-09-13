"""Pure procurement budget arithmetic; amounts are company-currency net item values."""

from decimal import Decimal


def number(value):
	return Decimal(str(value or 0))


def totals(rows):
	requests = {r["row"]: r for r in rows if r["kind"] == "request"}
	orders = {r["row"]: r for r in rows if r["kind"] == "order"}
	invoices = [r for r in rows if r["kind"] == "invoice"]
	reserved = committed = spent = Decimal(0)
	for invoice in invoices:
		spent += number(invoice["amount"])
	for key, order in orders.items():
		billed = sum((number(i["qty"]) for i in invoices if i.get("order") == key), Decimal(0))
		qty = number(order["qty"])
		if not order.get("closed") and qty > 0:
			committed += number(order["amount"]) * max(qty - billed, Decimal(0)) / qty
	for key, request in requests.items():
		covered = Decimal(0)
		for order in orders.values():
			if order.get("request") != key:
				continue
			qty = number(order["qty"])
			if order.get("closed"):
				qty = sum((number(i["qty"]) for i in invoices if i.get("order") == order["row"]), Decimal(0))
			covered += qty
		covered += sum(
			(number(i["qty"]) for i in invoices if i.get("request") == key and not i.get("order")), Decimal(0)
		)
		qty = number(request["qty"])
		if qty > 0:
			reserved += number(request["amount"]) * max(qty - covered, Decimal(0)) / qty
	return dict(reserved=reserved, committed=committed, spent=spent)
