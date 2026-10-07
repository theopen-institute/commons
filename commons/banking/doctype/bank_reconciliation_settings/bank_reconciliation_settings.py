"""How the bank reconciliation page guesses which loan a deposit repays, and
what kind of repayment it books.

Apart from Commons Settings because none of it is a switch on this app's
behaviour: it is tuning, and tuning that belongs to a lender. The weights a
site's statements reward depend on what its bank writes in a description --
whether payments carry the sender's name, an account number, or neither -- and
on how its borrowers pay. The defaults are the values the page was first
tuned with, so a site that never opens this form keeps them.

Read by `commons.banking.reconciliation`: the loan-matching weights travel to
the page in `loan_matching_settings`, and the repayment type is used by
`create_loan_repayments`. The rules themselves are the frontend's
(`frontend/src/data/reconciliationRules.ts`).

The defaults live in one place, this doctype's JSON: the form opens on them,
`loan_matching` reads them from the meta for a field with nothing stored, and
the frontend's fallback is read from the same JSON when it is built.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from commons.commons_core import apps

SETTINGS = "Bank Reconciliation Settings"

# The weights and thresholds the page scores loans by. Their defaults are the
# fields' own, in the JSON.
LOAN_MATCHING_FIELDS = (
	"party_match_score",
	"repeated_identifier_score",
	"single_identifier_score",
	"name_in_description_score",
	"exact_payoff_score",
	"usual_amount_score",
	"min_identifier_digits",
	"min_name_length",
)
DEFAULT_REPAYMENT_TYPE = "Normal Repayment"

LOAN_REPAYMENT = "Loan Repayment"


class BankReconciliationSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		default_repayment_type: DF.Autocomplete
		exact_payoff_score: DF.Int
		min_identifier_digits: DF.Int
		min_name_length: DF.Int
		name_in_description_score: DF.Int
		party_match_score: DF.Int
		repeated_identifier_score: DF.Int
		single_identifier_score: DF.Int
		usual_amount_score: DF.Int
	# end: auto-generated types

	def onload(self):
		"""The repayment types lending books from a bank statement, for the form to offer.

		The field is an Autocomplete rather than a Select because Lending is
		optional: on a site without it there is nothing to choose from, and the
		field takes what is typed. With Lending, `validate` holds it to Lending's
		list, so the effect is a Select whose options are Lending's.
		"""
		self.set_onload("repayment_types", repayment_types())

	def validate(self):
		if cint(self.min_identifier_digits) < 1:
			frappe.throw(_("An identifier is at least one digit long."))
		self.default_repayment_type = (self.default_repayment_type or "").strip() or DEFAULT_REPAYMENT_TYPE
		types = repayment_types()
		if types and self.default_repayment_type not in types:
			frappe.throw(
				_("{0} is not a repayment type Lending books from a bank statement: {1}").format(
					self.default_repayment_type, ", ".join(types)
				)
			)


def repayment_types() -> list[str]:
	"""The repayment types Lending itself books from a bank statement
	(`BANK_RECONCILIATION_REPAYMENT_TYPES`, what its own `create_loan_repayment_bts`
	accepts), or none on a site without Lending.

	Each of them posts to the repayment's own `payment_account`, which is what
	lets `create_loan_repayments` post to the statement's bank. The other types --
	waivers, adjustments, capitalisations -- post to accounts of the Loan
	Product's instead.
	"""
	if not apps.has_doctype(LOAN_REPAYMENT):
		return []
	try:
		from lending.loan_management.doctype.loan_repayment.loan_repayment import (
			BANK_RECONCILIATION_REPAYMENT_TYPES,
		)
	except ImportError:
		return []
	return list(BANK_RECONCILIATION_REPAYMENT_TYPES)


def loan_matching() -> dict[str, int]:
	"""The weights and thresholds, each the stored value or, with none, the field's default.

	A Single never saved loads its fields' defaults, but one saved before a field
	existed reads that field blank; the default then comes from the meta, so the
	JSON stays the only place it is kept.
	"""
	stored = _settings()
	meta = frappe.get_meta(SETTINGS)
	values = {}
	for field in LOAN_MATCHING_FIELDS:
		value = stored.get(field)
		if value is None or value == "":
			value = meta.get_field(field).default
		values[field] = max(0, cint(value))
	values["min_identifier_digits"] = max(1, values["min_identifier_digits"])
	return values


def default_repayment_type() -> str:
	"""The repayment type the page books, `Normal Repayment` unless the site says otherwise.

	Checked again here, not only when the form is saved, for a value saved before
	the list was narrowed to the types Lending books from a statement.
	"""
	repayment_type = (_settings().get("default_repayment_type") or "").strip() or DEFAULT_REPAYMENT_TYPE
	types = repayment_types()
	if types and repayment_type not in types:
		frappe.throw(
			_(
				"Bank Reconciliation Settings' Repayment Type {0} is not one Lending books from a bank statement: {1}"
			).format(repayment_type, ", ".join(types))
		)
	return repayment_type


def _settings():
	"""The cached settings document."""
	return frappe.get_cached_doc(SETTINGS)
