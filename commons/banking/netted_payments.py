"""Journal entry lines that Payment Reconciliation offers as payments although
their own journal entry has already netted them, and the fix.

Payment Reconciliation builds its two sides from different places. The
invoices come from the payment ledger: a journal entry line that names no
voucher settles its own journal entry, so every such line on one account and
party, charge or refund, is summed into that entry's outstanding. The
payments come from the journal entry's lines directly
(`PaymentReconciliation.get_jv_entries`): any line on the paying side with an
empty Reference is offered as an unallocated payment. Nothing checks the one
against the other, so a refund line in an entry that also charges the same
party is counted on both sides:

* ACC-JV-2025-00142 credits HR-EMP-00005 750 on TDS 11211 and credits -75 (a
  refund). The invoice side shows 675, which has the refund in it, and the
  payment side offers the 75 again.
* ACC-JV-2024-00046-1 debits and credits the same 3,000 on the same account and
  party. It nets to nothing, so the invoice side never shows it, but the payment
  side offers the 3,000.

The fix is the one a reconciliation makes when such a line is matched against
its own entry: the line's Reference is set to the journal entry itself. The
payment ledger already says exactly that (the line settles its own entry), so
nothing in the payment ledger or the GL changes, and no amount moves; the line
just stops being offered as a payment. ERPNext did this itself on
ACC-JV-2025-00142's TDS 11112 refund when it was reconciled on 2026-05-08.

It is only right when the refunds do not exceed the charges they sit with. If
an entry pays out more on an account and party than it charges there, the
excess is a real unallocated payment; marking the lines would hide it, and
splitting a line of a submitted entry is not something to do automatically.
Those are listed and refused.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import escape_html, flt

from commons.banking.ledger_audit import REPAIR_ROLES, TOLERANCE

NETTED = "Refund already netted in its own entry"
EXCESS = "Pays out more than it charges: split by hand"

MAX_BULK = 200


def _lines(filters) -> list[dict]:
	"""The journal entry lines the question is about: submitted, on a
	receivable/payable account of the party type's own kind (the accounts
	Payment Reconciliation lets one choose), naming no voucher or naming their
	own entry. Lines that name an order are advances and are left out, as
	they settle nothing in this entry."""
	clauses = ["je.docstatus = 1", "je.company = %(company)s", "ifnull(jea.party, '') != ''"]
	values = {"company": filters.company}
	for field in ("account", "party_type", "party"):
		if filters.get(field):
			clauses.append(f"jea.{field} = %({field})s")
			values[field] = filters.get(field)
	if filters.get("voucher_no"):
		clauses.append("je.name = %(voucher_no)s")
		values["voucher_no"] = filters.voucher_no
	if filters.get("from_date"):
		clauses.append("je.posting_date >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		clauses.append("je.posting_date <= %(to_date)s")
		values["to_date"] = filters.to_date
	return frappe.db.sql(
		f"""
		select je.name as voucher_no, je.posting_date, jea.name as row_name, jea.idx,
			jea.account, jea.party_type, jea.party,
			if(pt.account_type = 'Receivable',
				jea.credit_in_account_currency - jea.debit_in_account_currency,
				jea.debit_in_account_currency - jea.credit_in_account_currency) as paying,
			ifnull(jea.reference_type, '') as reference_type
		from `tabJournal Entry` je
		join `tabJournal Entry Account` jea on jea.parent = je.name and jea.parenttype = 'Journal Entry'
		join `tabParty Type` pt on pt.name = jea.party_type
		join `tabAccount` a on a.name = jea.account and a.account_type = pt.account_type
		where {" and ".join(clauses)}
			and (ifnull(jea.reference_type, '') = ''
				or (jea.reference_type = 'Journal Entry' and jea.reference_name = je.name))
		""",
		values,
		as_dict=True,
	)


def find_netted_payments(filters) -> list[dict]:
	"""Every journal entry, account and party where a line is offered as a
	payment although the same entry charges that party there too."""
	filters = frappe._dict(filters)
	if not filters.get("company"):
		frappe.throw(_("Company is required"))
	if filters.get("voucher_type") and filters.voucher_type != "Journal Entry":
		return []

	groups = defaultdict(list)
	for line in _lines(filters):
		groups[(line.voucher_no, line.account, line.party_type, line.party)].append(line)

	found = []
	for (voucher_no, account, party_type, party), lines in groups.items():
		# Offered as payments: paying side, Reference empty.
		offered = [ln for ln in lines if flt(ln.paying) > 0 and not ln.reference_type]
		charged = sum(-flt(ln.paying) for ln in lines if flt(ln.paying) < 0)
		if not offered or charged <= TOLERANCE:
			continue
		paid = sum(flt(ln.paying) for ln in offered)
		found.append(
			frappe._dict(
				voucher_type="Journal Entry",
				voucher_no=voucher_no,
				posting_date=lines[0].posting_date,
				account=account,
				party_type=party_type,
				party=party,
				charged=round(charged, 2),
				offered=round(paid, 2),
				rows=", ".join(str(ln.idx) for ln in sorted(offered, key=lambda ln: ln.idx)),
				row_names=[ln.row_name for ln in offered],
				issue=NETTED if paid <= charged + TOLERANCE else EXCESS,
			)
		)
	found.sort(key=lambda r: (str(r.posting_date), r.voucher_no, r.account, r.party))
	return found


def for_display(rows) -> list[dict]:
	return [{k: v for k, v in r.items() if k != "row_names"} for r in rows]


def _find_for(voucher_no: str) -> list[dict]:
	company = frappe.db.get_value("Journal Entry", voucher_no, "company")
	if not company:
		frappe.throw(_("Journal Entry {0} not found").format(voucher_no))
	return find_netted_payments({"company": company, "voucher_no": voucher_no})


@frappe.whitelist()
def preview_netted(voucher_no: str) -> list[dict]:
	"""What the fix of one journal entry would mark, worked out on the server."""
	frappe.only_for(REPAIR_ROLES)
	return for_display(_find_for(voucher_no))


def _mark(voucher_no: str) -> dict:
	found = _find_for(voucher_no)
	if not found:
		return {"voucher_no": voucher_no, "status": "nothing to fix"}
	excess = [r for r in found if r.issue == EXCESS]
	if excess:
		frappe.throw(
			_("{0} pays {1} more than it charges on {2}; split that line by hand.").format(
				voucher_no, frappe.format(excess[0].offered - excess[0].charged, "Float"), excess[0].account
			)
		)

	for group in found:
		for row_name in group.row_names:
			frappe.db.set_value(
				"Journal Entry Account",
				row_name,
				{"reference_type": "Journal Entry", "reference_name": voucher_no},
			)

	items = "".join(
		"<li>{} · {} · row {}: {:,.2f}</li>".format(
			escape_html(r.account), escape_html(r.party), escape_html(r.rows), r.offered
		)
		for r in found
	)
	frappe.get_doc("Journal Entry", voucher_no).add_comment(
		"Info",
		_(
			"Refund lines already netted in this entry were referenced to the entry itself, "
			"so Payment Reconciliation no longer offers them as payments. No amounts changed."
		)
		+ f"<ul>{items}</ul>",
	)
	return {"voucher_no": voucher_no, "status": "fixed", "lines": sum(len(r.row_names) for r in found)}


@frappe.whitelist(methods=["POST"])
def fix_netted(voucher_no: str) -> dict:
	frappe.only_for(REPAIR_ROLES)
	return _mark(voucher_no)


@frappe.whitelist(methods=["POST"])
def fix_netted_many(vouchers: list | str) -> list[dict]:
	"""`fix_netted` for several journal entries, each alone."""
	frappe.only_for(REPAIR_ROLES)
	vouchers = frappe.parse_json(vouchers)
	if len(vouchers) > MAX_BULK:
		frappe.throw(_("At most {0} vouchers at a time").format(MAX_BULK))
	results = []
	for voucher_no in vouchers:
		frappe.db.savepoint("netted_fix")
		try:
			results.append(_mark(voucher_no))
		except Exception as e:
			frappe.db.rollback(save_point="netted_fix")
			frappe.clear_last_message()
			results.append({"voucher_no": voucher_no, "status": "failed", "error": str(e)})
	return results
