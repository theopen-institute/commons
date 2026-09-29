"""Open receivables and payables, account by account, party by party.

What the two reports (`Open Receivables`, `Open Payables`) show is every voucher
that is open *now* and was issued on or before the chosen date. That is not the
snapshot ERPNext's Accounts Receivable/Payable takes at its report date: there,
an invoice paid the day after the report date is still open. Here it is not,
because it is not open any more; the date only decides which vouchers are old
enough to be listed. So every payment ledger row counts, whatever its date, and
the date is compared with the voucher's own posting date alone.

How a ledger row finds its voucher follows Accounts Receivable, so the two agree
on what is outstanding: a row counts against the voucher it settles; a payment
against a credit note that itself settles an invoice counts against that
invoice; and a row whose voucher has no rows of its own on that account and
party (an advance against a Sales Order, say) stays with its own voucher.

The accounting dimension filters apply to a voucher's own ledger rows -- an
invoice's cost center is the one it was booked to, whatever the payment says.
Accounts Receivable filters every row instead, so there a payment booked to
another cost center stops counting against the invoice it paid; not here.
"""

from collections import defaultdict

import frappe
from erpnext.accounts.doctype.accounting_dimension.accounting_dimension import (
	get_accounting_dimensions,
	get_dimension_with_children,
)
from erpnext.accounts.report.financial_statements import get_cost_centers_with_children
from erpnext.accounts.utils import (
	build_qb_match_conditions,
	get_currency_precision,
	get_party_types_from_account_type,
)
from frappe import _, qb
from frappe.query_builder import Criterion
from frappe.utils import flt, getdate, today

# Where each voucher type keeps the reference a person would recognise it by.
REFERENCE_FIELDS = {
	"Purchase Invoice": "bill_no",
	"Sales Invoice": "po_no",
	"Journal Entry": "cheque_no",
	"Payment Entry": "reference_no",
}


def execute(filters, account_type):
	filters = frappe._dict(filters or {})
	if not filters.company:
		frappe.throw(_("Company is required"))
	filters.as_on = getdate(filters.as_on or today())
	precision = get_currency_precision() or 2
	company_currency = frappe.get_cached_value("Company", filters.company, "default_currency")

	rows = fetch_ledger(filters, account_type)
	returns = fetch_returns(filters.company, account_type, rows)
	vouchers = open_vouchers(balance(rows, returns), precision)
	vouchers = [v for v in vouchers if v.posting_date <= filters.as_on]
	vouchers = [v for v in vouchers if matches_dimensions(v, dimension_filters(filters))]
	add_details(vouchers)

	foreign = any(v.account_currency != company_currency for v in vouchers)
	data = tree(vouchers, getdate(today()), foreign)
	for row in data:
		row.currency = company_currency
	return (
		columns(account_type, foreign),
		data,
		None,
		None,
		summary(vouchers, company_currency, getdate(today())),
	)


# --- The ledger --------------------------------------------------------------


def fetch_ledger(filters, account_type):
	"""Every live payment ledger row on the company's receivable (payable)
	accounts, of any date. Dimension filters are not applied here, see above."""
	ple = qb.DocType("Payment Ledger Entry")
	dimensions = [d for d in dimension_fields() if frappe.get_meta("Payment Ledger Entry").has_field(d)]
	party_types = get_party_types_from_account_type(account_type)
	if filters.party_type:
		party_types = [p for p in party_types if p == filters.party_type]
	accounts = party_accounts(filters.company, account_type, filters.account)
	if not accounts or not party_types:
		return []

	query = (
		qb.from_(ple)
		.select(
			ple.account,
			ple.account_currency,
			ple.voucher_type,
			ple.voucher_no,
			ple.against_voucher_type,
			ple.against_voucher_no,
			ple.party_type,
			ple.party,
			ple.posting_date,
			ple.due_date,
			ple.amount,
			ple.amount_in_account_currency,
			*[ple[d] for d in dimensions],
		)
		.where(ple.company == filters.company)
		.where(ple.delinked == 0)
		.where(ple.account.isin(accounts))
		.where(ple.party_type.isin(party_types))
		.orderby(ple.posting_date)
		.orderby(ple.creation)
	)
	if filters.party:
		query = query.where(ple.party.isin(as_list(filters.party)))
	for condition in party_permission_conditions(ple, party_types):
		query = query.where(condition)
	if match_conditions := build_qb_match_conditions("Payment Ledger Entry"):
		query = query.where(Criterion.all(match_conditions))
	return query.run(as_dict=True)


def party_accounts(company, account_type, account=None):
	"""Leaf receivable (payable) accounts, under `account` if one is chosen --
	a group account is allowed and stands for the accounts under it."""
	filters = {"company": company, "account_type": account_type, "is_group": 0}
	if account:
		lft, rgt = frappe.get_cached_value("Account", account, ["lft", "rgt"])
		filters.update(lft=(">=", lft), rgt=("<=", rgt))
	return frappe.get_all("Account", filters=filters, pluck="name")


def party_permission_conditions(ple, party_types):
	"""Party is a dynamic link, so User Permissions on Customer or Supplier
	do not reach it by themselves (Accounts Receivable does the same)."""
	from frappe.core.doctype.user_permission.user_permission import get_user_permissions
	from frappe.permissions import get_allowed_docs_for_doctype

	user_permissions = get_user_permissions()
	for party_type in party_types:
		if party_type in user_permissions:
			allowed = get_allowed_docs_for_doctype(user_permissions[party_type], party_type)
			yield (ple.party_type != party_type) | ple.party.isin(allowed or [""])


def fetch_returns(company, account_type, rows):
	"""Credit (debit) notes that settle their original invoice rather than
	standing open themselves: {return: the invoice it returns against}."""
	doctype = "Sales Invoice" if account_type == "Receivable" else "Purchase Invoice"
	names = {r.against_voucher_no for r in rows if r.against_voucher_type == doctype}
	if not names:
		return {}
	return dict(
		frappe.get_all(
			doctype,
			filters={
				"company": company,
				"docstatus": 1,
				"is_return": 1,
				"update_outstanding_for_self": 0,
				"return_against": ("is", "set"),
				"name": ("in", list(names)),
			},
			fields=["name", "return_against"],
			as_list=True,
		)
	)


# --- Balances ----------------------------------------------------------------


def balance(rows, returns):
	"""Group ledger rows under the voucher each one counts against.

	Keyed (account, party_type, party, voucher_type, voucher_no). A voucher's
	`amount` is what its own rows add up to (the invoice total, the payment
	received); `outstanding` is every row that counts against it.
	"""
	own = {key(r, r.voucher_type, r.voucher_no) for r in rows}
	dimensions = dimension_fields()
	vouchers = {}

	def voucher(k, row):
		if k not in vouchers:
			vouchers[k] = frappe._dict(
				account=k[0],
				party_type=k[1],
				party=k[2],
				voucher_type=k[3],
				voucher_no=k[4],
				account_currency=row.account_currency,
				amount=0.0,
				outstanding=0.0,
				outstanding_in_account_currency=0.0,
				posting_date=None,
				first_seen=row.posting_date,
				due_date=None,
				dimensions=defaultdict(set),
			)
		return vouchers[k]

	for r in rows:
		against_type, against_no = r.against_voucher_type, r.against_voucher_no
		if against_no in returns and against_type in ("Sales Invoice", "Purchase Invoice"):
			against_no = returns[against_no]
		target = key(r, against_type, against_no)
		if target not in own:
			target = key(r, r.voucher_type, r.voucher_no)
		v = voucher(target, r)
		v.outstanding += flt(r.amount)
		v.outstanding_in_account_currency += flt(r.amount_in_account_currency)

		# The voucher's own rows say when it was issued, when it is due and
		# where it was booked, wherever their amounts ended up.
		mine = voucher(key(r, r.voucher_type, r.voucher_no), r)
		mine.amount += flt(r.amount)
		if not mine.posting_date or r.posting_date < mine.posting_date:
			mine.posting_date = r.posting_date
		if r.due_date and (not mine.due_date or r.due_date < mine.due_date):
			mine.due_date = r.due_date
		for d in dimensions:
			if r.get(d):
				mine.dimensions[d].add(r[d])

	return vouchers


def key(row, voucher_type, voucher_no):
	return (row.account, row.party_type, row.party, voucher_type, voucher_no)


def open_vouchers(vouchers, precision):
	"""The vouchers still open, in both company and account currency (as
	Accounts Receivable decides it: a rounding remainder in one alone is not)."""
	least = 1.0 / 10**precision
	found = []
	for v in vouchers.values():
		v.outstanding = flt(v.outstanding, precision)
		v.outstanding_in_account_currency = flt(v.outstanding_in_account_currency, precision)
		if abs(v.outstanding) >= least and abs(v.outstanding_in_account_currency) >= least:
			v.posting_date = getdate(v.posting_date or v.first_seen)
			v.amount = flt(v.amount, precision)
			found.append(v)
	return found


# --- Dimensions --------------------------------------------------------------


def dimension_fields():
	return ["cost_center", "project", *get_accounting_dimensions()]


def dimension_filters(filters):
	"""{fieldname: the chosen values, with every child of a tree value}."""
	chosen = {}
	if filters.get("cost_center"):
		chosen["cost_center"] = set(get_cost_centers_with_children(as_list(filters.cost_center)))
	if filters.get("project"):
		chosen["project"] = set(as_list(filters.project))
	for dimension in get_accounting_dimensions(as_list=False):
		values = as_list(filters.get(dimension.fieldname))
		if not values:
			continue
		if frappe.get_cached_value("DocType", dimension.document_type, "is_tree"):
			values = get_dimension_with_children(dimension.document_type, values)
		chosen[dimension.fieldname] = set(values)
	return chosen


def matches_dimensions(voucher, chosen):
	"""A voucher matches when one of its own rows carries a chosen value, for
	every dimension filtered on (a journal entry may span several)."""
	return all(voucher.dimensions.get(field, set()) & values for field, values in chosen.items())


def as_list(value):
	if not value:
		return []
	if isinstance(value, str):
		value = frappe.parse_json(value) if value.startswith("[") else [value]
	return list(value)


# --- Details for the open vouchers alone -------------------------------------


def add_details(vouchers):
	by_type = defaultdict(set)
	for v in vouchers:
		by_type[v.voucher_type].add(v.voucher_no)
	references = {}
	for doctype, names in by_type.items():
		field = REFERENCE_FIELDS.get(doctype)
		if field and frappe.get_meta(doctype).has_field(field):
			for name, ref in frappe.get_all(
				doctype, filters={"name": ("in", list(names))}, fields=["name", field], as_list=True
			):
				references[(doctype, name)] = ref

	names = party_names(vouchers)
	for v in vouchers:
		v.reference = references.get((v.voucher_type, v.voucher_no))
		v.party_name = names.get((v.party_type, v.party)) or v.party
		v.cost_center = ", ".join(sorted(v.dimensions.get("cost_center", ())))


def party_names(vouchers):
	by_type = defaultdict(set)
	for v in vouchers:
		by_type[v.party_type].add(v.party)
	names = {}
	for party_type, parties in by_type.items():
		meta = frappe.get_meta(party_type)
		title = meta.title_field or {
			"Customer": "customer_name",
			"Supplier": "supplier_name",
			"Employee": "employee_name",
		}.get(party_type)
		if not title or not meta.has_field(title):
			continue
		for name, label in frappe.get_all(
			party_type, filters={"name": ("in", list(parties))}, fields=["name", title], as_list=True
		):
			names[(party_type, name)] = label
	return names


# --- The tree ----------------------------------------------------------------


def tree(vouchers, on, foreign):
	"""Account rows at the top, each party under its account, each voucher
	under its party; every group row carries its totals. A grand total last."""
	data = []
	accounts = defaultdict(lambda: defaultdict(list))
	for v in vouchers:
		accounts[v.account][(v.party_type, v.party)].append(v)

	for account in sorted(accounts):
		parties = accounts[account]
		members = [v for vs in parties.values() for v in vs]
		data.append(group_row("account", account, 0, members, on, foreign, account=account))
		for party_type, party in sorted(parties, key=lambda p: (parties[p][0].party_name or "").lower()):
			vs = sorted(parties[(party_type, party)], key=lambda v: (v.posting_date, v.voucher_no))
			data.append(
				group_row(
					"party",
					vs[0].party_name if vs[0].party_name == party else f"{vs[0].party_name} ({party})",
					1,
					vs,
					on,
					foreign,
					account=account,
					party_type=party_type,
					party=party,
				)
			)
			data.extend(voucher_row(v, on, foreign) for v in vs)

	if data:
		data.append(group_row("total", _("Total"), 0, vouchers, on, False))
	return data


def group_row(row_type, label, indent, vouchers, on, foreign, **extra):
	row = frappe._dict(
		row_type=row_type,
		label=label,
		indent=indent,
		vouchers=len(vouchers),
		amount=sum(v.amount for v in vouchers),
		outstanding=sum(v.outstanding for v in vouchers),
		overdue=sum(v.outstanding for v in vouchers if overdue_days(v, on)),
		**extra,
	)
	if row_type == "account":
		row.parties = len({(v.party_type, v.party) for v in vouchers})
	if foreign and row_type != "total":
		row.account_currency = vouchers[0].account_currency
		row.outstanding_in_account_currency = sum(v.outstanding_in_account_currency for v in vouchers)
	row.settled = row.amount - row.outstanding
	return row


def voucher_row(v, on, foreign):
	row = frappe._dict(
		row_type="voucher",
		label=v.voucher_no,
		indent=2,
		account=v.account,
		party_type=v.party_type,
		party=v.party,
		voucher_type=v.voucher_type,
		voucher_no=v.voucher_no,
		posting_date=v.posting_date,
		due_date=v.due_date,
		reference=v.reference,
		cost_center=v.cost_center,
		amount=v.amount,
		settled=v.amount - v.outstanding,
		outstanding=v.outstanding,
		overdue=v.outstanding if overdue_days(v, on) else 0.0,
		days_overdue=overdue_days(v, on),
	)
	if foreign:
		row.account_currency = v.account_currency
		row.outstanding_in_account_currency = v.outstanding_in_account_currency
	return row


def overdue_days(v, on):
	"""Days past due today (the voucher's posting date when it has no due
	date); nothing for a payment or credit waiting to be allocated."""
	if v.outstanding <= 0:
		return 0
	return max(0, (on - getdate(v.due_date or v.posting_date)).days)


def summary(vouchers, currency, on):
	outstanding = sum(v.outstanding for v in vouchers)
	overdue = sum(v.outstanding for v in vouchers if overdue_days(v, on))
	unallocated = sum(v.outstanding for v in vouchers if v.outstanding < 0)
	return [
		{"label": _("Outstanding"), "value": outstanding, "datatype": "Currency", "currency": currency},
		{
			"label": _("Overdue"),
			"value": overdue,
			"datatype": "Currency",
			"currency": currency,
			"indicator": "Red" if overdue else "Green",
		},
		{
			"label": _("Unallocated credits"),
			"value": unallocated,
			"datatype": "Currency",
			"currency": currency,
		},
		{"label": _("Parties"), "value": len({(v.party_type, v.party) for v in vouchers}), "datatype": "Int"},
		{"label": _("Open vouchers"), "value": len(vouchers), "datatype": "Int"},
	]


# --- Columns -----------------------------------------------------------------


def columns(account_type, foreign):
	settled = _("Received") if account_type == "Receivable" else _("Paid")
	cols = [
		{"fieldname": "label", "label": _("Account / Party / Voucher"), "fieldtype": "Data", "width": 320},
		{"fieldname": "voucher_type", "label": _("Voucher Type"), "fieldtype": "Data", "width": 130},
		{"fieldname": "posting_date", "label": _("Posting Date"), "fieldtype": "Date", "width": 105},
		{"fieldname": "due_date", "label": _("Due Date"), "fieldtype": "Date", "width": 105},
		{"fieldname": "reference", "label": _("Reference"), "fieldtype": "Data", "width": 130},
		{"fieldname": "vouchers", "label": _("Vouchers"), "fieldtype": "Int", "width": 80},
		money("amount", _("Amount")),
		money("settled", settled),
		money("outstanding", _("Outstanding")),
		money("overdue", _("Overdue")),
		{"fieldname": "days_overdue", "label": _("Days Overdue"), "fieldtype": "Int", "width": 100},
	]
	if foreign:
		cols += [
			{
				"fieldname": "outstanding_in_account_currency",
				"label": _("Outstanding (Account Currency)"),
				"fieldtype": "Currency",
				"options": "account_currency",
				"width": 150,
			},
			{"fieldname": "account_currency", "label": _("Currency"), "fieldtype": "Data", "width": 80},
		]
	cols.append(
		{
			"fieldname": "cost_center",
			"label": _("Cost Center"),
			"fieldtype": "Data",
			"width": 150,
		}
	)
	return cols


def money(fieldname, label):
	return {
		"fieldname": fieldname,
		"label": label,
		"fieldtype": "Currency",
		"options": "currency",
		"width": 130,
	}
