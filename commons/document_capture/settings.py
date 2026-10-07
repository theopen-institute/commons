"""Document Capture Settings, as the capture code reads them.

The rules a site chooses for its captures: which kinds it takes in, the extra
words a supplier's name is matched without, and how many reads one person may
have in an hour (`hourly_limit`), since every read is billed. Its Additional
Instructions and tax terms are read by `commons.document_capture.locale`, for
every document-reading prompt, bank statements included. Who sees a capture is the
role permissions' (`commons.document_capture.capture`). Each kind's switch is
named by the kind's own module (`ENABLE_FIELD`), and the kinds themselves are
`capture.KINDS`; nothing here lists them.

Read from the document cache. A never-saved Single loads with the doctype's
own defaults (`Document.load_from_db`), so a site that never opens the form
gets them without anything here restating them.
"""

import re
from functools import lru_cache

import frappe
from frappe.utils import cint

SETTINGS = "Document Capture Settings"


def _settings():
	"""The cached settings document."""
	return frappe.get_cached_doc(SETTINGS)


def value(fieldname: str):
	"""One setting."""
	return _settings().get(fieldname)


def enabled(kind) -> bool:
	"""Whether this site captures `kind`, a module of `capture.KINDS`."""
	return bool(value(kind.ENABLE_FIELD))


def hourly_limit() -> int:
	"""Reads one person may have in an hour; 0 for no limit."""
	return max(cint(value("hourly_limit")), 0)


def legal_words() -> frozenset[str]:
	"""The site's own words to ignore in a supplier's or company's name."""
	return _parse_words(value("supplier_legal_words") or "")


@lru_cache(maxsize=16)
def _parse_words(text: str) -> frozenset[str]:
	"""One word per line, in lower case and without punctuation, as `_words`
	in `purchase_invoice` compares them. A line of two words ("Pte Ltd") gives
	both."""
	return frozenset(re.sub(r"[^0-9a-z]+", " ", text.lower()).split())
