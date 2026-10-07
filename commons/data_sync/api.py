"""The endpoints behind the Data Sync page, on both of its sites.

The page runs on the site being changed (production) and reads the source
(a development copy) through the browser: production cannot reach a laptop, the
laptop's browser can reach both. So the same three read endpoints answer on
both sides -- `manifest`, `record`, `snapshot` -- and the source is called
cross-origin with an API key, which needs the page's origin in the source's
`allow_cors`. Nothing here ever connects from one site to the other.

A record's attached files travel with it: the page asks this site which it
lacks (`missing_files`), reads them from the source (`file`) and passes them to
`apply`. See `files.py`.

`apply` and `delete` are the only writes, and they run on the site the page is
on, one record at a time, from the page's details modal. Each carries the hash
the page saw for this site's copy and refuses if the record has changed since,
so a compare that has gone stale cannot overwrite somebody's edit.

Everything is System Manager only. The records are the site's configuration --
scripts, permissions, report queries -- not something to hand any desk user.
"""

import json

import frappe
from frappe import _
from frappe.model import no_value_fields, table_fields
from frappe.permissions import setup_custom_perms

from commons.data_sync import files as sync_files
from commons.data_sync import records
from commons.data_sync import rules as sync_rules

# Doctypes whose records are written as an import (`frappe.flags.in_import`): see `apply`.
IMPORTED = {"Sidebar"}


def _guard():
	frappe.only_for("System Manager")


@frappe.whitelist()
def settings() -> dict:
	"""What the page needs to start: this site's rules and where its source is."""
	_guard()
	return {
		"site": frappe.local.site,
		"format": records.FORMAT,
		"source_url": sync_rules.source_url(),
		"rules": sync_rules.configured(),
	}


@frappe.whitelist()
def manifest(rules=None) -> dict:
	"""Every selected record's hash, per doctype.

	`rules` is the page's list -- the site being changed decides what both sides
	load. Without it, this site's own. A doctype that fails to load (not on this
	site, a bad filter) is reported under `errors`, not raised, so one bad rule
	does not hide the rest.
	"""
	_guard()
	selected = _rules(rules)

	entries, errors, duplicates = {}, {}, {}
	for rule in selected:
		doctype = rule["doctype"]
		try:
			loaded = records.load(rule)
		except Exception as e:
			errors[doctype] = _error_text(e)
			continue
		entries[doctype] = {
			key: [records.hash_of(r["doc"], rule), r["name"], r["modified"], r["label"]]
			for key, r in loaded.items()
		}
		dupes = {key: r["duplicates"] for key, r in loaded.items() if r.get("duplicates")}
		if dupes:
			duplicates[doctype] = dupes

	return {
		"site": frappe.local.site,
		"format": records.FORMAT,
		"rules": selected,
		"entries": entries,
		"errors": errors,
		"duplicates": duplicates,
	}


@frappe.whitelist()
def record(rule, key: str) -> dict:
	"""One record's content on this site."""
	_guard()
	rule = sync_rules.parse(rule)[0]
	found = records.find(rule, key)
	return {
		"doc": found["doc"] if found else None,
		"name": found["name"] if found else None,
		"modified": found["modified"] if found else None,
		"hash": records.hash_of(found["doc"], rule) if found else None,
	}


@frappe.whitelist()
def snapshot(rules=None) -> dict:
	"""The manifest with every record's content, to save as a file.

	For when the page cannot reach the source live -- another browser, another
	machine, the source not running. The page on the source downloads it; the
	page on the site being changed loads it in place of the live source.
	"""
	_guard()
	selected = _rules(rules)
	out = manifest(rules=selected)
	out["records"] = {}
	out["files"] = {}
	for rule in selected:
		if rule["doctype"] in out["errors"]:
			continue
		loaded = {key: r["doc"] for key, r in records.load(rule).items()}
		out["records"][rule["doctype"]] = loaded
		for doc in loaded.values():
			for url in sync_files.urls_in(rule["doctype"], doc):
				if url not in out["files"]:
					out["files"][url] = sync_files.export(url)
	return out


@frappe.whitelist()
def file(url: str) -> dict | None:
	"""One of this site's files, for the site a record is being copied to."""
	_guard()
	return sync_files.export(url)


@frappe.whitelist()
def missing_files(rule, doc) -> list[str]:
	"""The files `doc`, the source's content, attaches that this site lacks."""
	_guard()
	rule = sync_rules.parse(rule)[0]
	doc = json.loads(doc) if isinstance(doc, str) else doc
	return sync_files.missing(sync_files.urls_in(rule["doctype"], doc))


@frappe.whitelist(methods=["POST"])
def apply(rule, key: str, doc, expected: str | None = None, files=None) -> dict:
	"""Make this site's record match `doc`, the source's content. Returns the new state.

	Inserts when this site has no record with the key, otherwise updates it.
	Every field the doctype declares is set from `doc`, a field absent from it
	is cleared, and each child table is replaced with the source's rows. Fields
	the rule ignores keep this site's values on an update.

	Goes through `insert` and `save` with permissions checked, so the doctype's
	own validation runs: a link to something this site lacks fails with Frappe's
	message naming it, and copying what it depends on first is the fix.

	`files` are the source's files the record attaches and this site lacked, as
	`missing_files` listed and the source's `file` returned. They are written
	first, the record is pointed at them, and they are attached to it once saved.
	"""
	_guard()
	rule = sync_rules.parse(rule)[0]
	doc = json.loads(doc) if isinstance(doc, str) else doc
	doctype = rule["doctype"]
	meta = frappe.get_meta(doctype)

	current = _check_unchanged(rule, key, expected)

	files = json.loads(files) if isinstance(files, str) else files
	written = sync_files.restore(files)
	sync_files.rewrite(doctype, doc, written)

	# A doctype's first Custom DocPerm replaces all of its standard permissions,
	# so one copied row alone would lock every other role out. Copy the standard
	# rows in first, as the Role Permission Manager does; the row being applied
	# may then exist already.
	if doctype == "Custom DocPerm" and doc.get("parent") and setup_custom_perms(doc["parent"]):
		current = records.find(rule, key)

	if meta.issingle:
		target = frappe.get_single(doctype)
	elif current:
		target = frappe.get_doc(doctype, current["name"])
	else:
		target = frappe.new_doc(doctype)

	ignored = set(rule["ignored_fields"]) if current else set()
	for df in meta.fields:
		if df.fieldname in ignored or df.fieldtype == "Password":
			continue
		# Before the `no_value_fields` test: Frappe counts Table fields among them.
		if df.fieldtype in table_fields:
			target.set(df.fieldname, [])
			for row in doc.get(df.fieldname) or []:
				target.append(df.fieldname, {k: v for k, v in row.items() if k != "idx"})
		elif df.fieldtype not in no_value_fields:
			target.set(df.fieldname, doc.get(df.fieldname))

	# A site's own `Sidebar` can only be saved in developer mode, because Frappe
	# counts a sidebar as its app's content -- except when it arrives by import,
	# which a copy from another site is. Only for this doctype: elsewhere the
	# flag relaxes checks a copy should still pass.
	importing = doctype in IMPORTED and not frappe.flags.in_import
	if importing:
		frappe.flags.in_import = True
	try:
		if target.is_new() and not meta.issingle:
			target.insert(set_name=None if rule["key_fields"] else key)
		else:
			target.save()
	finally:
		if importing:
			frappe.flags.in_import = False

	if doctype == "Custom DocPerm":
		frappe.clear_cache(doctype=target.parent)

	sync_files.attach(list(written.values()), doctype, target.name)

	return _state(rule, key)


@frappe.whitelist(methods=["POST"])
def delete(rule, key: str, expected: str | None = None) -> dict:
	"""Delete this site's record with the key, the source having none."""
	_guard()
	rule = sync_rules.parse(rule)[0]
	current = _check_unchanged(rule, key, expected)
	if not current:
		frappe.throw(_("This site has no such record."))
	if frappe.get_meta(rule["doctype"]).issingle:
		frappe.throw(_("A Single cannot be deleted."))
	frappe.delete_doc(rule["doctype"], current["name"])
	if rule["doctype"] == "Custom DocPerm":
		frappe.clear_cache(doctype=current["doc"].get("parent"))
	return _state(rule, key)


def _check_unchanged(rule: dict, key: str, expected: str | None) -> dict | None:
	current = records.find(rule, key)
	now = records.hash_of(current["doc"], rule) if current else None
	if now != (expected or None):
		frappe.throw(
			_("This record has changed on this site since you compared. Compare again before copying."),
			title=_("Changed Since Compare"),
		)
	return current


def _state(rule: dict, key: str) -> dict:
	found = records.find(rule, key)
	if not found:
		return {"hash": None, "name": None, "modified": None, "label": ""}
	return {
		"hash": records.hash_of(found["doc"], rule),
		"name": found["name"],
		"modified": found["modified"],
		"label": found["label"],
	}


def _rules(value) -> list[dict]:
	return sync_rules.parse(value) if value else sync_rules.configured()


def _error_text(e: Exception) -> str:
	if isinstance(e, frappe.DoesNotExistError) or "doesn't exist" in str(e):
		return _("Not on this site.")
	return frappe.utils.strip_html(str(e)) or e.__class__.__name__
