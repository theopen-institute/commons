"""Does the payment ledger say what the general ledger says, and the repair when
it does not.

ERPNext keeps two ledgers for receivable and payable accounts. The GL is the
books. The Payment Ledger is a copy of the GL's receivable/payable lines, kept
per party and per voucher that they settle, and it is what the Accounts
Receivable and Accounts Payable reports, payment reconciliation and every
invoice's `outstanding_amount` read. The copy is made at submit and undone at
cancel by `erpnext.accounts.utils.create_payment_ledger_entry`, and it only
copies lines on accounts whose Account Type is Receivable or Payable *at that
moment*. Change an account's type between a voucher's submit and its cancel and
the two ledgers part: on one site, a TDS account's type was blank for five
days, eight payroll JEs were cancelled in between, and their lines on that
account stayed live in the Payment Ledger (and in Accounts Payable) with
nothing in the GL behind them.

`find_discrepancies` asks the question the copy should always answer yes to.
For every voucher, account and party, the live Payment Ledger amount (rows with
`delinked = 0`) must equal the net of the voucher's live GL lines
(`is_cancelled = 0`), signed the way ERPNext signs them. A cancelled voucher
nets to zero in the GL, so its live payment ledger rows must too.

Which voucher a line settles is deliberately not part of the comparison. When a
payment or journal entry is reconciled after submit,
`erpnext.accounts.utils.reconcile_against_document` rebuilds its payment ledger
rows from the document, split per invoice, and leaves the GL as posted, so the
GL line still names no invoice. Only the totals per voucher, account and party
are the same in both ledgers. That rebuild is also a second way for the two to
part: a journal entry reconciled while that account's type was blank had its
lines on it dropped from the payment ledger.

The repair changes only the Payment Ledger; the GL is the books and nothing
here writes to it. For each voucher, account and party that disagrees, the
live rows are marked delinked (the state ERPNext's own cancel leaves them in,
so the history stays readable) and, for a submitted voucher, replaced by rows
rebuilt from the document the way ERPNext rebuilds them (`build_gl_map` for
payments and journal entries, `get_gl_entries` otherwise). Rebuilding from the
GL instead would undo every reconciliation. The rebuilt rows must add up to
the GL; where they do not (the document says something the GL does not), the
repair refuses and says so, because then it is the books that need a person.
A cancelled voucher only has its rows delinked.

ERPNext's Repost Payment Ledger rebuilds the same way but covers submitted
invoices, payments and journal entries only, never a cancelled voucher; it
rebuilds every voucher in a date range rather than the ones that are wrong,
checks nothing against the GL, and deletes the rows it replaces.

`find_outstanding_discrepancies` is the second question: does an invoice's
`outstanding_amount` field say what the payment ledger says it is owed? The
repair there is ERPNext's `update_voucher_outstanding`, which recomputes the
field from the payment ledger. It is only right once the payment ledger is,
which is why the report lists ledger problems first.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from commons.commons_core import apps

# Half a paisa/cent. Anything smaller is float noise in the sums.
TOLERANCE = 0.005

# Who may run the repairs here and in `loan_dates` and `netted_payments`: they
# write ledger rows, so they are for the people who may already close the
# books. Write on Period Closing Voucher, which posts GL itself, is what a
# stock ERPNext site grants Accounts Manager and System Manager, and nobody
# else; a site that wants others to repair grants it in Role Permissions.
REPAIR_DOCTYPE = "Period Closing Voucher"


def can_repair() -> bool:
	"""Whether this user may run the ledger repairs. The reports ask the same
	question in the browser, with `frappe.model.can_write`."""
	return bool(frappe.has_permission(REPAIR_DOCTYPE, "write"))


def check_can_repair() -> None:
	"""Refuse, as `frappe.only_for` would, unless `can_repair`."""
	if not can_repair():
		frappe.throw(
			_("Repairing the ledger needs write permission on {0}.").format(_(REPAIR_DOCTYPE)),
			frappe.PermissionError,
		)


# The most vouchers one bulk request repairs. Each is its own savepoint, so a
# refusal costs only that voucher; the cap keeps one request short.
MAX_BULK = 200

# The issue a discrepancy is filed under, most specific first.
CANCELLED = "Cancelled voucher still in payment ledger"
NOT_RP = "Account is no longer Receivable/Payable"
MISSING = "Missing from payment ledger"
# Missing too, but the GL line names no party: posted while the account was
# not yet Receivable/Payable. Accounts Payable has never shown it, so adding
# it is a choice, not a correction.
MISSING_NO_PARTY = "Missing from payment ledger, no party"
EXTRA = "In payment ledger but not in GL"
DIFFERS = "Amounts differ"

# Invoice-like doctypes whose `outstanding_amount` ERPNext keeps from the
# payment ledger (`erpnext.accounts.utils.OUTSTANDING_DOCTYPES`), with the
# account and party each posts its receivable/payable line to.
OUTSTANDING_SOURCES = {
	"Sales Invoice": ("debit_to", "'Customer'", "customer"),
	"Purchase Invoice": ("credit_to", "'Supplier'", "supplier"),
	"Fees": ("receivable_account", "'Student'", "student"),
}

KEY_FIELDS = ("voucher_type", "voucher_no", "account", "party_type", "party")


def _key(row) -> tuple:
	return tuple(row.get(f) or "" for f in KEY_FIELDS)


def _conditions(filters, alias: str, date_field: str = "posting_date") -> tuple[str, dict]:
	"""The optional filters as SQL, on the table aliased `alias`."""
	clauses = [f"{alias}.company = %(company)s"]
	values = {"company": filters.company}
	for field in ("account", "party_type", "party", "voucher_type", "voucher_no"):
		if filters.get(field):
			clauses.append(f"{alias}.{field} = %({field})s")
			values[field] = filters.get(field)
	if filters.get("from_date"):
		clauses.append(f"{alias}.{date_field} >= %(from_date)s")
		values["from_date"] = filters.from_date
	if filters.get("to_date"):
		clauses.append(f"{alias}.{date_field} <= %(to_date)s")
		values["to_date"] = filters.to_date
	return " and ".join(clauses), values


def _gl_amounts(filters) -> dict:
	"""The live GL, netted per key, signed as ERPNext signs payment ledger rows.

	The against-voucher defaults are `get_payment_ledger_entries`'s: a line
	that settles nothing settles its own voucher. Period Closing Vouchers are
	left out because ERPNext never copies them.
	"""
	where, values = _conditions(filters, "g")
	rows = frappe.db.sql(
		f"""
		select g.voucher_type, g.voucher_no, g.account,
			ifnull(g.party_type, '') as party_type, ifnull(g.party, '') as party,
			max(g.posting_date) as posting_date,
			sum(if(a.account_type = 'Receivable', g.debit - g.credit, g.credit - g.debit)) as amount,
			sum(if(a.account_type = 'Receivable',
				g.debit_in_account_currency - g.credit_in_account_currency,
				g.credit_in_account_currency - g.debit_in_account_currency)) as amount_in_account_currency
		from `tabGL Entry` g
		join `tabAccount` a on a.name = g.account
		where {where}
			and g.is_cancelled = 0
			and a.account_type in ('Receivable', 'Payable')
			and g.voucher_type != 'Period Closing Voucher'
		group by 1, 2, 3, 4, 5
		""",
		values,
		as_dict=True,
	)
	return {_key(r): r for r in rows}


def _ple_amounts(filters) -> dict:
	"""The live payment ledger, summed per key, on any account."""
	where, values = _conditions(filters, "p")
	rows = frappe.db.sql(
		f"""
		select p.voucher_type, p.voucher_no, p.account,
			ifnull(p.party_type, '') as party_type, ifnull(p.party, '') as party,
			max(p.posting_date) as posting_date,
			sum(p.amount) as amount,
			sum(p.amount_in_account_currency) as amount_in_account_currency
		from `tabPayment Ledger Entry` p
		where {where} and p.delinked = 0 and p.docstatus < 2
		group by 1, 2, 3, 4, 5
		""",
		values,
		as_dict=True,
	)
	return {_key(r): r for r in rows}


def _receivable_payable_accounts(company: str) -> set[str]:
	return set(
		frappe.get_all(
			"Account",
			filters={"company": company, "account_type": ["in", ["Receivable", "Payable"]]},
			pluck="name",
		)
	)


def _docstatuses(vouchers: set[tuple[str, str]]) -> dict:
	"""The docstatus of each (voucher_type, voucher_no), None where it is gone."""
	by_type = defaultdict(list)
	for voucher_type, voucher_no in vouchers:
		by_type[voucher_type].append(voucher_no)
	statuses = {}
	for voucher_type, names in by_type.items():
		if not apps.has_doctype(voucher_type):
			continue
		for row in frappe.get_all(
			voucher_type, filters={"name": ["in", names]}, fields=["name", "docstatus"]
		):
			statuses[(voucher_type, row.name)] = row.docstatus
	return statuses


def _issue(docstatus, account_is_rp: bool, gl: float, ple: float) -> str:
	if docstatus == 2 and abs(ple) > TOLERANCE:
		return CANCELLED
	if not account_is_rp:
		return NOT_RP
	if abs(ple) <= TOLERANCE:
		return MISSING
	if abs(gl) <= TOLERANCE:
		return EXTRA
	return DIFFERS


def find_discrepancies(filters) -> list[dict]:
	"""Every key on which the live payment ledger and the live GL disagree."""
	filters = frappe._dict(filters)
	if not filters.get("company"):
		frappe.throw(_("Company is required"))

	gl = _gl_amounts(filters)
	ple = _ple_amounts(filters)
	rp_accounts = _receivable_payable_accounts(filters.company)

	found = []
	for key in gl.keys() | ple.keys():
		g, p = gl.get(key) or {}, ple.get(key) or {}
		gl_amount, ple_amount = flt(g.get("amount")), flt(p.get("amount"))
		gl_acc, ple_acc = (
			flt(g.get("amount_in_account_currency")),
			flt(p.get("amount_in_account_currency")),
		)
		if abs(ple_amount - gl_amount) <= TOLERANCE and abs(ple_acc - gl_acc) <= TOLERANCE:
			continue
		found.append(
			frappe._dict(
				zip(KEY_FIELDS, key, strict=True),
				posting_date=g.get("posting_date") or p.get("posting_date"),
				gl_amount=gl_amount,
				ple_amount=ple_amount,
				difference=flt(ple_amount - gl_amount, 2),
				account_is_rp=key[2] in rp_accounts,
			)
		)

	statuses = _docstatuses({(r.voucher_type, r.voucher_no) for r in found})
	for row in found:
		row.voucher_status = {0: "Draft", 1: "Submitted", 2: "Cancelled"}.get(
			statuses.get((row.voucher_type, row.voucher_no)), "Missing"
		)
		row.issue = _issue(
			statuses.get((row.voucher_type, row.voucher_no)),
			row.pop("account_is_rp"),
			row.gl_amount,
			row.ple_amount,
		)
		if row.issue == MISSING and not row.party:
			row.issue = MISSING_NO_PARTY
	found.sort(key=lambda r: (str(r.posting_date or ""), r.voucher_no, r.account, r.party))
	return found


def find_outstanding_discrepancies(filters) -> list[dict]:
	"""Submitted invoices whose `outstanding_amount` is not what the payment
	ledger says is still owed on them."""
	filters = frappe._dict(filters)
	found = []
	for doctype, (account_field, party_type, party_field) in OUTSTANDING_SOURCES.items():
		if filters.get("voucher_type") and filters.voucher_type != doctype:
			continue
		if not apps.has_doctype(doctype):
			continue
		meta = frappe.get_meta(doctype)
		if not all(meta.has_field(f) for f in (account_field, party_field, "outstanding_amount")):
			continue
		clauses = ["d.docstatus = 1", "d.company = %(company)s"]
		values = {"company": filters.company}
		if filters.get("voucher_no"):
			clauses.append("d.name = %(voucher_no)s")
			values["voucher_no"] = filters.voucher_no
		if filters.get("party"):
			clauses.append(f"d.{party_field} = %(party)s")
			values["party"] = filters.party
		if filters.get("party_type"):
			clauses.append(f"{party_type} = %(party_type)s")
			values["party_type"] = filters.party_type
		if filters.get("account"):
			clauses.append(f"d.{account_field} = %(account)s")
			values["account"] = filters.account
		if filters.get("from_date"):
			clauses.append("d.posting_date >= %(from_date)s")
			values["from_date"] = filters.from_date
		if filters.get("to_date"):
			clauses.append("d.posting_date <= %(to_date)s")
			values["to_date"] = filters.to_date
		rows = frappe.db.sql(
			f"""
			select '{doctype}' as voucher_type, d.name as voucher_no, d.posting_date,
				d.{account_field} as account, {party_type} as party_type, d.{party_field} as party,
				d.outstanding_amount as recorded,
				ifnull((select sum(p.amount_in_account_currency)
					from `tabPayment Ledger Entry` p
					where p.against_voucher_type = '{doctype}' and p.against_voucher_no = d.name
						and p.account = d.{account_field} and p.party = d.{party_field}
						and p.delinked = 0 and p.docstatus < 2), 0) as ledger
			from `tab{doctype}` d
			where {" and ".join(clauses)}
			having abs(recorded - ledger) > {TOLERANCE}
			""",
			values,
			as_dict=True,
		)
		for row in rows:
			row.difference = flt(flt(row.recorded) - flt(row.ledger), 2)
		found.extend(rows)
	found.sort(key=lambda r: (str(r.posting_date or ""), r.voucher_no))
	return found


# The repair


def _rebuilt_entries(doc) -> list | None:
	"""The payment ledger rows ERPNext would make for this document now, or
	None where the doctype offers no way to rebuild them.

	The same two sources ERPNext's own rebuilds use: `build_gl_map` is what
	reconciliation uses for payments and journal entries, and `get_gl_entries`
	is what Repost Payment Ledger uses for the rest.
	"""
	from erpnext.accounts.utils import get_payment_ledger_entries

	if hasattr(doc, "build_gl_map"):
		gl_map = doc.build_gl_map()
	elif hasattr(doc, "get_gl_entries"):
		gl_map = doc.get_gl_entries()
	else:
		return None
	return [e for e in get_payment_ledger_entries(gl_map) if e.doctype == "Payment Ledger Entry"]


def _plan(voucher_type: str, voucher_no: str) -> frappe._dict:
	"""What the repair of one voucher would change, worked out from the ledgers
	as they are now, never from what a browser sent.

	`refused` says why the voucher cannot be repaired here; the plan is then
	shown but not applied.
	"""
	company = frappe.db.get_value(
		"Payment Ledger Entry", {"voucher_type": voucher_type, "voucher_no": voucher_no}, "company"
	) or frappe.db.get_value("GL Entry", {"voucher_type": voucher_type, "voucher_no": voucher_no}, "company")
	if not company:
		frappe.throw(_("{0} {1} has no ledger entries").format(voucher_type, voucher_no))

	issues = find_discrepancies({"company": company, "voucher_type": voucher_type, "voucher_no": voucher_no})
	plan = frappe._dict(company=company, issues=issues, delink=[], add=[], refused=None)
	if not issues:
		return plan
	bad = {_key(r): r for r in issues}

	live = [
		r
		for r in frappe.get_all(
			"Payment Ledger Entry",
			filters={"voucher_type": voucher_type, "voucher_no": voucher_no, "delinked": 0, "docstatus": 1},
			fields=[
				"name",
				"voucher_type",
				"voucher_no",
				"posting_date",
				"account",
				"party_type",
				"party",
				"against_voucher_type",
				"against_voucher_no",
				"amount",
			],
		)
		if _key(r) in bad
	]
	plan.delink = live

	if issues[0].voucher_status != "Submitted":
		# Cancelled, or gone: nothing in the GL, so nothing to rebuild.
		return plan

	rebuilt = _rebuilt_entries(frappe.get_doc(voucher_type, voucher_no))
	if rebuilt is None:
		plan.refused = _("{0} cannot be rebuilt here; repost it with ERPNext's own tools.").format(
			voucher_type
		)
		return plan
	rebuilt = [e for e in rebuilt if _key(e) in bad]
	plan.delink, plan.add = _differing(live, rebuilt)

	totals = defaultdict(float)
	for e in rebuilt:
		totals[_key(e)] += flt(e.amount)
	wrong = [r for key, r in bad.items() if abs(totals[key] - r.gl_amount) > TOLERANCE]
	if wrong:
		plan.refused = _(
			"Rebuilt from the document, {0} would come to {1}, but the GL says {2}. "
			"The document and its GL disagree, so this needs to be looked at by hand."
		).format(
			wrong[0].account,
			frappe.format(totals[_key(wrong[0])], "Float"),
			frappe.format(wrong[0].gl_amount, "Float"),
		)
	return plan


def _differing(live: list, rebuilt: list) -> tuple[list, list]:
	"""The live rows with no identical rebuilt row, and the rebuilt rows with
	no identical live row. Rows already right are left alone, so the repair
	touches only what is wrong."""

	def match(r):
		return (*_key(r), r.against_voucher_type or "", r.against_voucher_no or "", round(flt(r.amount), 2))

	unmatched = list(rebuilt)
	delink = []
	for row in live:
		twin = next((e for e in unmatched if match(e) == match(row)), None)
		if twin is None:
			delink.append(row)
		else:
			unmatched.remove(twin)
	return delink, unmatched


def _public(plan) -> dict:
	"""The plan as the dialog shows it."""
	fields = (
		"posting_date",
		"account",
		"party_type",
		"party",
		"against_voucher_type",
		"against_voucher_no",
		"amount",
	)
	return {
		"issues": plan.issues,
		"delink": [{f: r.get(f) for f in fields} for r in plan.delink],
		"add": [{f: e.get(f) for f in fields} for e in plan.add],
		"refused": plan.refused,
	}


@frappe.whitelist()
def preview_repair(voucher_type: str, voucher_no: str) -> dict:
	"""What the repair of one voucher would do, for the dialog to show before
	anything is written."""
	check_can_repair()
	return _public(_plan(voucher_type, voucher_no))


def _repair(voucher_type: str, voucher_no: str) -> dict:
	from erpnext.accounts.utils import update_voucher_outstanding

	plan = _plan(voucher_type, voucher_no)
	if not plan.issues:
		return {"voucher_no": voucher_no, "status": "nothing to repair"}
	if plan.refused:
		frappe.throw(plan.refused)

	touched = set()
	for row in plan.delink:
		frappe.db.set_value("Payment Ledger Entry", row.name, "delinked", 1)
		touched.add(
			(row.against_voucher_type, row.against_voucher_no, row.account, row.party_type, row.party)
		)

	for entry in plan.add:
		ple = frappe.get_doc(entry)
		ple.flags.ignore_permissions = True
		# ERPNext's own repost flag: the GL line was validated when it was
		# posted, and the frozen-account and dimension checks are for new
		# postings, not for copying an old one.
		ple.flags.from_repost = True
		ple.flags.update_outstanding = "No"
		ple.submit()
		touched.add(
			(ple.against_voucher_type, ple.against_voucher_no, ple.account, ple.party_type, ple.party)
		)

	# Every invoice whose rows moved, once the ledger is final.
	for against_type, against_no, account, party_type, party in touched:
		if (
			against_type
			and apps.has_doctype(against_type)
			and frappe.db.get_value(against_type, against_no, "docstatus") == 1
		):
			update_voucher_outstanding(against_type, against_no, account, party_type, party)

	items = "".join(
		"<li>{} · {} · {}: GL {:,.2f}, payment ledger {:,.2f}</li>".format(
			frappe.utils.escape_html(r.account),
			frappe.utils.escape_html(r.party or "-"),
			frappe.utils.escape_html(r.issue),
			r.gl_amount,
			r.ple_amount,
		)
		for r in plan.issues
	)
	frappe.get_doc(voucher_type, voucher_no).add_comment(
		"Info",
		_(
			"Payment ledger repaired to match the general ledger: {0} row(s) delinked, {1} row(s) added."
		).format(len(plan.delink), len(plan.add))
		+ f"<ul>{items}</ul>",
	)
	return {
		"voucher_no": voucher_no,
		"status": "repaired",
		"delinked": len(plan.delink),
		"added": len(plan.add),
	}


@frappe.whitelist(methods=["POST"])
def repair_voucher(voucher_type: str, voucher_no: str) -> dict:
	"""Make one voucher's payment ledger agree with its GL."""
	check_can_repair()
	return _repair(voucher_type, voucher_no)


@frappe.whitelist(methods=["POST"])
def repair_vouchers(vouchers: list | str) -> list[dict]:
	"""`repair_voucher` for several, each alone: a refusal skips only that one."""
	check_can_repair()
	vouchers = frappe.parse_json(vouchers)
	if len(vouchers) > MAX_BULK:
		frappe.throw(_("At most {0} vouchers at a time").format(MAX_BULK))
	results = []
	for v in vouchers:
		frappe.db.savepoint("ledger_repair")
		try:
			results.append(_repair(v["voucher_type"], v["voucher_no"]))
		except Exception as e:
			frappe.db.rollback(save_point="ledger_repair")
			frappe.clear_last_message()
			results.append({"voucher_no": v["voucher_no"], "status": "failed", "error": str(e)})
	return results


@frappe.whitelist(methods=["POST"])
def repair_outstanding(voucher_type: str, voucher_no: str) -> dict:
	"""Recompute an invoice's outstanding amount from the payment ledger."""
	from erpnext.accounts.utils import update_voucher_outstanding

	check_can_repair()
	if voucher_type not in OUTSTANDING_SOURCES:
		frappe.throw(_("{0} has no outstanding amount to recompute").format(voucher_type))
	account_field, party_type, party_field = OUTSTANDING_SOURCES[voucher_type]
	doc = frappe.get_doc(voucher_type, voucher_no)
	if doc.docstatus != 1:
		frappe.throw(_("{0} {1} is not submitted").format(voucher_type, voucher_no))
	before = flt(doc.outstanding_amount)
	update_voucher_outstanding(
		voucher_type, voucher_no, doc.get(account_field), party_type.strip("'"), doc.get(party_field)
	)
	after = flt(frappe.db.get_value(voucher_type, voucher_no, "outstanding_amount"))
	doc.add_comment(
		"Info",
		_("Outstanding amount recomputed from the payment ledger: {0} → {1}.").format(
			frappe.format(before, "Float"), frappe.format(after, "Float")
		),
	)
	return {"voucher_no": voucher_no, "before": before, "after": after}
