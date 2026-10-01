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
(`frontend/src/data/reconciliationRules.ts`), which has the same defaults as
its fallbacks.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint

from commons.commons_core import apps

SETTINGS = "Bank Reconciliation Settings"

# Each field's own default as well, so the form opens on these. Here too
# because a site between this app landing and its migrate has no doctype to
# read them from.
LOAN_MATCHING_DEFAULTS = {
	"party_match_score": 8,
	"repeated_identifier_score": 6,
	"single_identifier_score": 2,
	"name_in_description_score": 5,
	"exact_payoff_score": 2,
	"usual_amount_score": 1,
	"min_identifier_digits": 6,
	"min_name_length": 5,
}
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
		"""Lending's own repayment types, for the form to offer.

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
				_("{0} is not one of Lending's repayment types: {1}").format(
					self.default_repayment_type, ", ".join(types)
				)
			)


def repayment_types() -> list[str]:
	"""`Loan Repayment.repayment_type`'s options, or none on a site without Lending."""
	if not apps.has_doctype(LOAN_REPAYMENT):
		return []
	field = frappe.get_meta(LOAN_REPAYMENT).get_field("repayment_type")
	return [option for option in (field.options or "").split("\n") if option] if field else []


def loan_matching() -> dict[str, int]:
	"""The weights and thresholds, each the stored value or, with none, the default.

	A Single that has never been saved still reads as its fields' defaults, so
	the fallback here is for the window before migrate, when there is no
	doctype at all.
	"""
	stored = _settings()
	values = {}
	for field, default in LOAN_MATCHING_DEFAULTS.items():
		value = stored.get(field) if stored else None
		values[field] = default if value is None else max(0, cint(value))
	values["min_identifier_digits"] = max(1, values["min_identifier_digits"])
	return values


def default_repayment_type() -> str:
	"""The repayment type the page books, `Normal Repayment` unless the site says otherwise."""
	stored = _settings()
	return (
		(stored.get("default_repayment_type") if stored else None) or ""
	).strip() or DEFAULT_REPAYMENT_TYPE


def _settings():
	"""The cached settings document, or None between this app landing and its migrate.

	The same guard as `commons.commons_core.settings._settings`: a Single whose
	doctype is not there yet raises `ImportError`, and that is an answer here
	rather than a fault -- unless the doctype is there, which makes it one.
	"""
	try:
		return frappe.get_cached_doc(SETTINGS)
	except (ImportError, frappe.DoesNotExistError):
		if frappe.db.exists("DocType", SETTINGS):
			raise
		return None
