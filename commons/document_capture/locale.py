"""Where the documents come from, as the prompts that read them describe it.

Reading an invoice, a receipt or a bank statement turns on a few facts that
belong to the site rather than to the app: which currency a bare "$" or "Rs."
most likely means, what the local tax registration number and withholding tax
are called, and whether dates may be printed in Bikram Sambat. Each prompt
takes them from a `Locale`, built by `for_company` from this site's data:

* the Company's `country` and `default_currency`, for the company the document
  is read for. Nothing has been read yet when the prompt is written, so that is
  the reader's default company (`default_company`), and a site with a single
  company needs none.
* Commons Settings' Bikram Sambat switch. Only where it is on does the schema
  offer `"BS"` as a calendar and the prompt explain it; elsewhere every date is
  asked for in the Gregorian calendar, and `"AD"` is the only answer allowed.
* Document Capture Settings' Additional Instructions, which `finish` puts
  after the app's own rules, for whatever this site's documents do that no app
  could know.

The tax terms are Document Capture Settings' Tax ID Name and Withholding Tax
Name where the site has set them, and otherwise derived from the country (`TAX_TERMS`),
which knows only a few; anywhere else the prompt says "tax registration
number" and "withholding tax", which read correctly anywhere.

Every function that writes prompt text is pure: it takes a `Locale` and returns
a string or a schema, so the prompts are tested without a site.

It lives here rather than beside the Claude client because it reads this site's
doctypes (Company, Commons Settings, Document Capture Settings), which an
integration never does (`commons.api_integrations`). Bank statement import
(`commons.banking.statement_import`) borrows it, as it borrows Document
Capture's way of reading a scan.
"""

import datetime
from dataclasses import dataclass

import frappe

from commons.document_capture import settings as capture_settings

COMPANY = "Company"

AD = "AD"
BS = "BS"

NEPAL = "Nepal"

# What a country calls its tax registration number and the tax a buyer
# withholds from a payment, where that is well known. Only these are named in a
# prompt, and only for a company in that country, unless Document Capture
# Settings names the site's own (`tax_id_name`, `withholding_tax_name`), which win.
TAX_TERMS = {
	NEPAL: {"tax_id": "PAN or VAT number", "withholding": "TDS"},
	"India": {"tax_id": "GSTIN or PAN", "withholding": "TDS"},
}

# The Bikram Sambat years a document is likely to be dated in, around this
# year's: old enough for a statement of past years, a little ahead for a due
# date. In 2026 that is 2075 to 2090.
BS_YEARS_BEFORE = 8
BS_YEARS_AFTER = 7


@dataclass(frozen=True)
class Locale:
	"""What a prompt is told about where its documents come from.

	The defaults describe nothing in particular: no country, no currency, the
	Gregorian calendar only, and no instructions or tax terms of the site's own.
	"""

	country: str | None = None
	currency: str | None = None
	bikram_sambat: bool = False
	additional_instructions: str = ""
	# Document Capture Settings' names for the tax terms, over the country's.
	tax_id_name: str = ""
	withholding_tax_name: str = ""

	@property
	def calendars(self) -> list[str]:
		return [AD, BS] if self.bikram_sambat else [AD]

	@property
	def tax_terms(self) -> dict:
		"""The country's terms from `TAX_TERMS`, each replaced by the site's own
		where Document Capture Settings names one."""
		terms = dict(TAX_TERMS.get(self.country or "", {}))
		if self.tax_id_name.strip():
			terms["tax_id"] = self.tax_id_name.strip()
		if self.withholding_tax_name.strip():
			terms["withholding"] = self.withholding_tax_name.strip()
		return terms


def for_company(company: str | None = None) -> Locale:
	"""The `Locale` of `company`, or of `default_company` when none is named.

	Only the country and currency of a company are read, which say nothing a
	reader could not see on any of its invoices, so no permission is asked.
	"""
	from commons.commons_core import settings

	company = company or default_company()
	values = (
		frappe.get_cached_value(COMPANY, company, ["country", "default_currency"], as_dict=True)
		if company
		else None
	) or {}
	return Locale(
		country=values.get("country") or None,
		currency=values.get("default_currency") or None,
		bikram_sambat=settings.feature_enabled(settings.ENABLE_BIKRAM_SAMBAT),
		additional_instructions=_setting("additional_instructions"),
		tax_id_name=_setting("tax_id_name"),
		withholding_tax_name=_setting("withholding_tax_name"),
	)


def _setting(fieldname: str) -> str:
	"""A Document Capture Settings text, trimmed; empty where unset."""
	return (capture_settings.value(fieldname) or "").strip()


def default_company() -> str | None:
	"""The company a document is most likely for before it has been read: the
	session user's default (which falls back to the site's), or the only
	company there is."""
	default = frappe.defaults.get_user_default("Company")
	if default and frappe.db.exists(COMPANY, default):
		return default
	companies = frappe.get_all(COMPANY, pluck="name", limit=2)
	return companies[0] if len(companies) == 1 else None


# --------------------------------------------------------------------------- #
# Schemas                                                                      #
# --------------------------------------------------------------------------- #


def calendar_schema(locale: Locale) -> dict:
	"""The `calendar` of a date: `AD`, and `BS` only where it is switched on."""
	if locale.bikram_sambat:
		return {
			"type": "string",
			"enum": locale.calendars,
			"description": "BS for a Bikram Sambat date, AD for a Gregorian one.",
		}
	return {"type": "string", "enum": locale.calendars, "description": "AD: the Gregorian calendar."}


def date_schema(locale: Locale) -> dict:
	"""A date as printed, with its year, month and day in `calendar`."""
	properties = {
		"printed": {"type": "string", "description": "The date exactly as printed."},
		"year": {"type": "integer"},
		"month": {"type": "integer", "description": "1 to 12."},
		"day": {"type": "integer"},
		"calendar": calendar_schema(locale),
	}
	return {
		"type": "object",
		"properties": properties,
		"required": list(properties),
		"additionalProperties": False,
	}


# --------------------------------------------------------------------------- #
# Prompt text                                                                  #
# --------------------------------------------------------------------------- #


def bs_years(today: datetime.date | None = None) -> tuple[int, int]:
	"""The range of Bikram Sambat years a document is likely to be dated in.

	A Bikram Sambat year begins in mid-April, 57 years ahead of the Gregorian
	one, and 56 ahead before then. Roughly is enough: it is a hint, and the
	browser checks each date against the real tables when it converts it.
	"""
	today = today or datetime.date.today()
	year = today.year + (57 if (today.month, today.day) >= (4, 14) else 56)
	return year - BS_YEARS_BEFORE, year + BS_YEARS_AFTER


def date_rule(locale: Locale, documents: str, today: datetime.date | None = None) -> str:
	"""How dates are given, for `documents` ("invoices", "receipts").

	With Bikram Sambat on, as printed and unconverted, since a model asked to
	convert one does the arithmetic badly; the browser converts them. Without
	it, only the Gregorian calendar is offered.
	"""
	if not locale.bikram_sambat:
		return (
			"Dates: give each as printed, then its Gregorian year, month and day, "
			'with calendar "AD". If a date is printed in more than one calendar, '
			"give the Gregorian one."
		)
	first, last = bs_years(today)
	often = (
		f"{documents.capitalize()} are often dated"
		if locale.country == NEPAL
		else f"Some {documents} are dated"
	)
	return (
		f"Dates: give each as printed, then its year, month and day. {often} in "
		"Bikram Sambat (B.S. or वि.सं.), the calendar used in Nepal, whose years "
		f'currently run from about {first} to {last}. Mark those calendar "BS" and '
		"give the Bikram Sambat year, month and day as printed; do not convert "
		'them. Mark Gregorian dates "AD". If both are printed, give the Gregorian '
		"one."
	)


def currency_rule(locale: Locale, document: str) -> str:
	"""How the currency is given, for a `document` ("invoice", "statement").

	A symbol several currencies share is read as this company's currency,
	where the company has one, since that is where its documents mostly come
	from.
	"""
	rule = (
		f"currency: the ISO 4217 code of the currency the {document} is in, such as "
		"USD for US dollars or INR for Indian rupees; null if it cannot be told."
	)
	if locale.currency:
		country = f" (country: {locale.country})" if locale.country else ""
		rule += (
			f" The company reading it keeps its books in {locale.currency}{country}: "
			f"where the {document} shows only a symbol or word several currencies "
			'share, such as "$" or "Rs.", and nothing else on it points to another '
			f"currency, give {locale.currency}."
		)
	return rule


def tax_id_name(locale: Locale) -> str:
	"""What a party's tax number is called: the site's or the country's term,
	where there is one (`Locale.tax_terms`), and "tax registration number"
	either way."""
	known = locale.tax_terms.get("tax_id")
	return f"{known} (or other tax registration number)" if known else "tax registration number"


def withholding_name(locale: Locale) -> str:
	"""The tax a buyer withholds from what it pays, by the site's or the
	country's name for it where there is one."""
	known = locale.tax_terms.get("withholding")
	return f"withholding tax ({known})" if known else "withholding tax"


def finish(instructions: str, locale: Locale) -> str:
	"""`instructions`, with the site's Additional Instructions after them."""
	extra = (locale.additional_instructions or "").strip()
	if not extra:
		return instructions
	return f"{instructions.rstrip()}\n\nThis site's own instructions for its documents:\n{extra}\n"
