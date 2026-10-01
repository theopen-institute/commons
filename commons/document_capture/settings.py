"""Document Capture Settings, read safely.

The rules a site chooses for its captures: which kinds it takes in, who sees a
capture of each kind, the role that sees all of them, and the extra words a
supplier's name is matched without. Each kind's fields are named by the kind's
own module (`ENABLE_FIELD`, `VISIBILITY_FIELD`), and the kinds themselves are
`capture.KINDS`; nothing here lists them.

Read the way `commons.commons_core.settings._settings` reads Commons Settings:
from the document cache, and as the defaults below between this app landing
and the migrate that creates the doctype. The defaults are the rules as they
were hard-coded, so a site that never opens the form behaves as it did.
"""

import re
from functools import lru_cache

import frappe

SETTINGS = "Document Capture Settings"

# The two answers to "who besides the sender sees a capture of this kind".
ANYONE = "Anyone who may create the drafted document"
SENDER_ONLY = "Sender only"

# The doctype's own defaults, for a site that has no doctype to read them from.
# `test_capture` holds these equal to the JSON.
DEFAULTS = {
	"enable_purchase_invoices": 1,
	"enable_expense_claims": 1,
	"purchase_invoice_visibility": ANYONE,
	"expense_claim_visibility": SENDER_ONLY,
	"supervisor_role": "System Manager",
	"supplier_legal_words": "",
}


def _settings():
	"""The cached settings document, or None between this app landing and its
	migrate. See `commons.commons_core.settings._settings`, whose reasoning this
	follows."""
	try:
		return frappe.get_cached_doc(SETTINGS)
	except (ImportError, frappe.DoesNotExistError):
		if frappe.db.exists("DocType", SETTINGS):
			raise
		return None


def value(fieldname: str):
	"""A setting, or its default where the site has no doctype yet.

	A never-saved Single loads with its defaults already (`Document.load_from_db`),
	so only the missing doctype needs `DEFAULTS`.
	"""
	doc = _settings()
	return DEFAULTS.get(fieldname) if doc is None else doc.get(fieldname)


def enabled(kind) -> bool:
	"""Whether this site captures `kind`, a module of `capture.KINDS`."""
	return bool(value(kind.ENABLE_FIELD))


def visibility(kind) -> str:
	"""Who besides the sender sees a capture of `kind`: `ANYONE` or
	`SENDER_ONLY`. Anything unrecognised is read as the narrower."""
	return ANYONE if value(kind.VISIBILITY_FIELD) == ANYONE else SENDER_ONLY


def supervisor_role() -> str | None:
	"""The role whose holders see every capture, or None for nobody but
	Administrator."""
	return (value("supervisor_role") or "").strip() or None


def legal_words() -> frozenset[str]:
	"""The site's own words to ignore in a supplier's or company's name."""
	return _parse_words(value("supplier_legal_words") or "")


@lru_cache(maxsize=16)
def _parse_words(text: str) -> frozenset[str]:
	"""One word per line, in lower case and without punctuation, as `_words`
	in `purchase_invoice` compares them. A line of two words ("Pte Ltd") gives
	both."""
	return frozenset(re.sub(r"[^0-9a-z]+", " ", text.lower()).split())
