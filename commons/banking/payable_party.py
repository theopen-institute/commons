"""A payment's own party on its tax and deduction lines to payable accounts.

Withholding is money owed to the tax office on a supplier's behalf, and a site
that wants to see it per supplier keeps its TDS accounts as Payable, so that
each withheld line carries the party it was withheld from and the Accounts
Payable report shows it against them. ERPNext does not allow for this on a
Payment Entry: its Advance Taxes and Charges and its Deductions post to any
account with no party at all, and a party-less line on a Payable account is
then refused ("Party Type and Party is required for Receivable / Payable
account").

The obvious fix is a GL Entry (and Payment Ledger Entry) `before_insert` that
copies the payment's party onto such a line, and it is the wrong place.
ERPNext builds every ledger row of a payment from one in-memory list,
`build_gl_map`, and it matches rows against that list, not against what was
saved. On cancel, `create_payment_ledger_entry` marks the original payment
ledger rows delinked by matching account, party type, party and against
voucher -- with the list's party-less line, before any `before_insert` has run
-- so the original withheld row stays live and the cancelled payment stays on
Accounts Payable. Reconciliation (`reconcile_against_document`), Repost
Accounting Ledger and this app's own ledger repair (`ledger_audit`) all rebuild
from the same list, and all miss the same way.

So the party goes on the list itself, here. Every row ERPNext derives from it,
at submit, cancel, reconciliation, repost or in the draft's ledger preview,
then carries it, and the matches ERPNext makes are the ones it already knows
how to make.

Only lines on Payable accounts that have no party are touched, and only with
the payment's own party. The payment's party line already has it; bank, expense
and income lines are left alone, since ERPNext refuses a party on those.
Receivable accounts are not included: nothing has asked for them.
"""

import frappe

from commons.commons_core.settings import ENABLE_PAYABLE_PARTY, feature_enabled


def fill_payable_party(gl_entries: list, party_type: str | None, party: str | None) -> None:
	"""Give each party-less line on a Payable account this party, in place."""
	if not (party_type and party):
		return
	for entry in gl_entries:
		if entry.get("party"):
			continue
		if frappe.get_cached_value("Account", entry.get("account"), "account_type") != "Payable":
			continue
		entry["party_type"] = party_type
		entry["party"] = party


class PayablePartyPaymentEntryMixin:
	def build_gl_map(self):
		gl_entries = super().build_gl_map()
		if feature_enabled(ENABLE_PAYABLE_PARTY):
			fill_payable_party(gl_entries, self.party_type, self.party)
		return gl_entries
