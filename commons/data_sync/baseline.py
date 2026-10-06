"""What both sites looked like the moment one was copied from the other.

Comparing two sites directly says only *that* a record differs. It cannot tell
"added on the source" from "deleted here", or "edited on the source" from
"edited here" -- and copying the source's version over an edit made here loses
that edit silently. A third copy settles it: the record as it was when the sites
were last identical. Whichever side still matches it is the side that did not
change.

The source (a development copy of production) records it straight after the
copy is restored and *before* its migrate, which would rewrite fixture fields
to the source's code:

    bench --site register.localhost execute commons.data_sync.baseline.record

`pull-prod.sh` runs this. The baseline is stored as cleaned records rather than
hashes, so the page can still hash it under rules changed since -- different
key fields or ignored fields -- and show the old values beside the two current
ones when both sides changed. It lives in the site's private folder, outside
`private/files`, so it is no File record and no restore overwrites it.

Each doctype is recorded with the rule's filters as they stood then. A doctype
added to the rules afterwards has no baseline, and the page falls back to
comparing the two sites directly for it.
"""

import gzip
import json
import os

import frappe
from frappe.utils import now

from commons.data_sync import records, rules


def path() -> str:
	return frappe.get_site_path("private", "data_sync", "baseline.json.gz")


def record() -> str:
	"""Store every record the rules select, as they are now. Returns a summary.

	Records the defaults as well as this site's own rules: right after a restore
	the settings table may not exist yet, and a broader baseline is never wrong.
	"""
	selected = {rule["doctype"]: rule for rule in map(rules.normalise, rules.DEFAULT_RULES)}
	selected.update({rule["doctype"]: rule for rule in rules.configured()})

	stored = {}
	for doctype, rule in selected.items():
		if not frappe.db.exists("DocType", doctype):
			continue
		stored[doctype] = {
			"rule": rule,
			"records": {r["name"]: r["doc"] for r in records.load(rule).values()},
		}

	data = {"format": records.FORMAT, "site": frappe.local.site, "taken_at": now(), "doctypes": stored}
	os.makedirs(os.path.dirname(path()), exist_ok=True)
	with gzip.open(path(), "wt", encoding="utf-8") as f:
		json.dump(data, f, default=str)

	count = sum(len(d["records"]) for d in stored.values())
	return f"Data Sync baseline: {count} records in {len(stored)} doctypes, {path()}"


def read() -> dict | None:
	try:
		with gzip.open(path(), "rt", encoding="utf-8") as f:
			data = json.load(f)
	except FileNotFoundError:
		return None
	return data if data.get("format") == records.FORMAT else None


def keyed(data: dict, rule: dict) -> dict[str, dict] | None:
	"""The baseline's records for the rule's doctype, keyed by the rule. None: not recorded."""
	stored = (data or {}).get("doctypes", {}).get(rule["doctype"])
	if stored is None:
		return None
	return {records.record_key(name, doc, rule): doc for name, doc in stored["records"].items()}
