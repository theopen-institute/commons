"""Journal entries that move no money at the bank, cleared on their own date.

A site that keeps each department's money in one shared bank account moves
money between departments with a journal entry that credits the bank account
under one department and debits it under the other (ACC-JV-2026-00182: 20,000
from Notes from the Field to Fellowship (Tsering), both on Laxmi Bank). Each
department's share of the bank balance changes; the bank balance does not.

Clearance asks when the bank processed what a voucher moved through it, and
such an entry moved nothing. No bank statement will ever carry a line for it,
so it waits in Bank Clearance and the Bank Reconciliation Statement until
somebody clears it by hand, to some date that means nothing. Its own posting
date is the one that is true: the entry is complete the day it is made.

ERPNext keeps one clearance date for the whole journal entry, not one per
line. So an entry is only cleared here when every bank and cash account on it
nets to nothing. One that also pays something out of another bank account is
still waiting for that payment to reach the statement, and is left alone.
Nets are taken per account, in the account's currency, because that is what
the bank sees.

An entry that already has a clearance date keeps it.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt

from commons.banking.ledger_audit import TOLERANCE
from commons.commons_core.settings import ENABLE_CLEAR_INTERNAL_TRANSFERS, feature_enabled

# The account types Bank Clearance and the Bank Reconciliation Statement offer.
CLEARED_ACCOUNT_TYPES = ("Bank", "Cash")


def moves_no_money(lines) -> bool:
	"""Whether these journal entry lines touch a bank or cash account, and net
	to nothing on every one they touch."""
	nets = defaultdict(float)
	for line in lines:
		if frappe.get_cached_value("Account", line.account, "account_type") in CLEARED_ACCOUNT_TYPES:
			nets[line.account] += flt(line.debit_in_account_currency) - flt(line.credit_in_account_currency)
	return bool(nets) and all(abs(net) < TOLERANCE for net in nets.values())


def clear_on_submit(doc, method=None) -> None:
	"""Journal Entry `on_submit`."""
	if not feature_enabled(ENABLE_CLEAR_INTERNAL_TRANSFERS) or doc.clearance_date:
		return
	if moves_no_money(doc.accounts):
		doc.db_set("clearance_date", doc.posting_date)


def clear_existing() -> list[str]:
	"""Clear the submitted journal entries posted before the setting was on.

	Returns the names cleared.
	"""
	candidates = frappe.db.sql_list(
		"""
		select distinct je.name
		from `tabJournal Entry` je
		join `tabJournal Entry Account` jea on jea.parent = je.name and jea.parenttype = 'Journal Entry'
		join `tabAccount` acc on acc.name = jea.account
		where je.docstatus = 1
			and je.clearance_date is null
			and acc.account_type in %(types)s
		""",
		{"types": CLEARED_ACCOUNT_TYPES},
	)
	cleared = []
	for name in candidates:
		lines = frappe.get_all(
			"Journal Entry Account",
			filters={"parent": name, "parenttype": "Journal Entry"},
			fields=["account", "debit_in_account_currency", "credit_in_account_currency"],
		)
		if moves_no_money(lines):
			posting_date = frappe.db.get_value("Journal Entry", name, "posting_date")
			frappe.db.set_value("Journal Entry", name, "clearance_date", posting_date, update_modified=False)
			cleared.append(name)
	return cleared


def clear_existing_when_switched_on(settings) -> None:
	"""Commons Settings `on_update`: the entries already waiting are cleared once,
	when the setting is ticked, so that switching it on means the same thing for
	old entries as for new ones."""
	before = settings.get_doc_before_save()
	if not settings.get(ENABLE_CLEAR_INTERNAL_TRANSFERS) or (
		before and before.get(ENABLE_CLEAR_INTERNAL_TRANSFERS)
	):
		return
	cleared = clear_existing()
	if cleared:
		frappe.msgprint(
			_("Cleared {0} journal entries that move no money at the bank, each on its posting date.").format(
				len(cleared)
			)
		)
