"""Records as Data Sync compares them: loaded in bulk, stripped to what a person
set, keyed, and hashed.

Two sites agree about a record when its *content* agrees, so everything that
says when or by whom it was saved goes: `modified`, `owner`, `creation`, the
underscore columns Frappe keeps for tags, likes and assignments, and on child
rows the `name` and `parent` links that differ by construction. `modified`
would also be the wrong test on its own -- saving a record unchanged bumps it,
and so do some migrates. It is kept beside the hash, for display only.

What is left is canonicalised before it is hashed, so the same content hashes
the same on both sites:

- empty values (None and "") are dropped, so a column one site has and the other
  lacks, left blank, is no difference;
- numbers that are whole become ints, so a Float field read back as `1.0` and a
  Check read back as `1` agree;
- dates and times become ISO text;
- only fields the doctype's meta declares are kept. Frappe never drops a column
  when a field is deleted, so a site carries leftovers the other may not;
- Password fields are left out entirely. Their column holds a placeholder, and
  the secret itself is not something to copy between sites;
- child rows keep their `idx`, since order is content (a report's columns, a
  workspace's links).

Change any of this and bump `FORMAT`: the page refuses to compare two sites
whose hashes were computed differently.
"""

import datetime
import hashlib
import json
from decimal import Decimal

import frappe
from frappe.model import no_value_fields, table_fields

# Which normalisation produced a hash. The page checks both sites report the same.
FORMAT = 1

PARENT_SKIP = frozenset(
	{"name", "owner", "creation", "modified", "modified_by", "idx", "doctype", "docstatus"}
)
CHILD_SKIP = frozenset(
	{
		"name",
		"owner",
		"creation",
		"modified",
		"modified_by",
		"doctype",
		"docstatus",
		"parent",
		"parenttype",
		"parentfield",
	}
)

# How many parent names go into one `IN (...)` when reading child rows.
CHUNK = 500


def load(rule: dict) -> dict[str, dict]:
	"""Every record the rule selects, as `{key: {"name", "modified", "label", "doc"}}`.

	One query for the parents and one per child table (in chunks), whatever the
	count -- `frappe.get_doc` per record would be a query per table per record.
	A key two records share keeps the first; `duplicates` reports the rest.
	"""
	doctype = rule["doctype"]
	meta = frappe.get_meta(doctype)

	if meta.issingle:
		doc = frappe.get_single(doctype).as_dict(no_nulls=True)
		children = {df.fieldname: doc.get(df.fieldname) or [] for df in meta.get_table_fields()}
		return {
			doctype: {
				"name": doctype,
				"modified": str(doc.get("modified") or ""),
				"label": "",
				"doc": clean(doc, meta, children),
			}
		}

	rows = frappe.get_all(
		doctype, filters=rule["filters"], fields=["*"], order_by="name asc", limit_page_length=0
	)
	children = _children(meta, [row.name for row in rows])
	title_field = meta.get_title_field() if meta.title_field else None

	records = {}
	for row in rows:
		doc = clean(row, meta, children.get(row.name, {}))
		key = record_key(row.name, doc, rule)
		if key in records:
			records[key].setdefault("duplicates", []).append(row.name)
			continue
		label = row.get(title_field) if title_field else None
		records[key] = {
			"name": row.name,
			"modified": str(row.modified or ""),
			"label": label if label and label != row.name else "",
			"doc": doc,
		}
	return records


def _children(meta, names: list[str]) -> dict[str, dict[str, list]]:
	"""`{parent name: {table fieldname: [rows in idx order]}}` for every table field."""
	out: dict[str, dict[str, list]] = {}
	for df in meta.get_table_fields():
		for start in range(0, len(names), CHUNK):
			rows = frappe.get_all(
				df.options,
				filters={
					"parenttype": meta.name,
					"parentfield": df.fieldname,
					"parent": ["in", names[start : start + CHUNK]],
				},
				fields=["*"],
				order_by="idx asc",
				limit_page_length=0,
			)
			for row in rows:
				out.setdefault(row.parent, {}).setdefault(df.fieldname, []).append(row)
	return out


def clean(row: dict, meta, children: dict[str, list]) -> dict:
	"""The record's content: what `hash_of` hashes and `apply` writes."""
	out = {}
	for fieldname, value in row.items():
		if fieldname in PARENT_SKIP or fieldname.startswith("_"):
			continue
		df = meta.get_field(fieldname)
		if (
			not df
			or df.fieldtype in no_value_fields
			or df.fieldtype in table_fields
			or df.fieldtype == "Password"
		):
			continue
		value = clean_value(value)
		if value is not None:
			out[fieldname] = value

	for df in meta.get_table_fields():
		rows = children.get(df.fieldname) or []
		if rows:
			child_meta = frappe.get_meta(df.options)
			out[df.fieldname] = [_clean_child(r, child_meta) for r in rows]
	return out


def _clean_child(row: dict, meta) -> dict:
	out = {}
	for fieldname, value in row.items():
		if fieldname in CHILD_SKIP or fieldname.startswith("_"):
			continue
		df = meta.get_field(fieldname)
		if fieldname != "idx" and (not df or df.fieldtype in no_value_fields or df.fieldtype == "Password"):
			continue
		value = clean_value(value)
		if value is not None:
			out[fieldname] = value
	return out


def clean_value(value):
	if value is None or value == "":
		return None
	if isinstance(value, bool):
		return int(value)
	if isinstance(value, float | Decimal):
		number = float(value)
		return int(number) if number.is_integer() else number
	if isinstance(value, datetime.datetime | datetime.date | datetime.time):
		return value.isoformat()
	if isinstance(value, datetime.timedelta):
		return str(value)
	if isinstance(value, bytes):
		return value.decode()
	return value


def record_key(name: str, doc: dict, rule: dict) -> str:
	"""What identifies the record on both sites: its name, or the rule's key fields.

	Key fields become a JSON list of their values as text, so `permlevel` 0 and
	"0" -- or a blank `if_owner` and a dropped one -- are the same key.
	"""
	if not rule["key_fields"]:
		return name
	return json.dumps([str(doc.get(f, "")) for f in rule["key_fields"]], ensure_ascii=False)


def hash_of(doc: dict, rule: dict) -> str:
	ignored = set(rule["ignored_fields"])
	content = {k: v for k, v in doc.items() if k not in ignored}
	text = json.dumps(content, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
	return hashlib.sha1(text.encode()).hexdigest()[:20]


def find(rule: dict, key: str) -> dict | None:
	"""The one record with this key, as `load` returns it, or None.

	Loads the whole rule rather than querying by key: the key is computed from
	cleaned content, so the same computation is the only way to be sure it finds
	what the manifest listed. The largest default doctype loads in well under a
	second.
	"""
	return load(rule).get(key)
