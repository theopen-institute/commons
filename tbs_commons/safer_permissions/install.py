# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Migrate hook for the gate: getting the changed checkbox in front of admins.

The gate column itself is three Custom Fields, one on each of the tables core
keeps permission flags in -- `Custom DocPerm`, `DocPerm` and `DocShare`, the last
because core's own permission types are: a share must not hand out what a gate
withholds. They are declared in `tbs_commons/fixtures/custom_field.json` and
written by Frappe's own fixture sync, so nothing here creates them.

Deliberately not a `Permission Type`. That core extension point registers one
record per doctype, can only be written during install, migrate or developer
mode, and draws its checkbox among the rights. The gate applies to every doctype
and belongs beside "Only if Creator", so a plain column plus
`public/js/permission_manager_gate.js` is both simpler and closer to the truth.

That script is what this hook is left to deal with: appending it to a core page
is the one part of the arrangement Frappe will not re-deliver on its own.
"""

from pathlib import Path

import frappe


def sync_permission_manager() -> None:
	"""Everything the gate asserts on both install and migrate."""
	_bust_permission_manager_cache()


# Where the last-deployed hash of the scripts below is kept, in `tabDefaultValue`.
# A site-level value rather than a cache entry on purpose: a Redis flush must not
# read as "the script changed" and make every desk re-fetch it.
GATE_JS_HASH_KEY = "tbs_commons_permission_manager_gate_hash"

# `__default` is the parent `frappe.db.set_default` writes under. Named here
# because the read below goes to the table rather than through
# `frappe.db.get_default`, which is served from a cache that is populated inside
# the transaction and not unwound with it. A migrate that wrote the hash and then
# failed would otherwise leave the cache claiming a hash the database never took,
# and the next migrate would match it and skip the one touch this whole function
# exists to make.
DEFAULTS_PARENT = "__default"

PERMISSION_MANAGER = "permission-manager"


def _bust_permission_manager_cache() -> None:
	"""Make every desk drop its cached copy of the Role Permission Manager.

	`page_js` is appended to that page's script, and the desk caches the whole
	script in `localStorage` under `_page:permission-manager` with no version
	check at all -- `pageview.js` uses the key if it merely exists. The one thing
	that does invalidate it is `sync_pages()` at desk boot, which deletes the key
	when the Page's `modified` differs from the copy it cached alongside it.

	So touching the record is how a change to the gate checkbox actually reaches
	anyone who has opened this page before -- and only when there is a change to
	reach them with. Touching it on every migrate would make every admin who has
	ever opened this page re-fetch a 20KB script after every deploy, almost always
	to arrive at a byte-identical copy.

	The hash is of the script's contents rather than its mtime: a checkout rewrites
	mtimes whether or not anything in the file moved, and what the desks are
	holding is the contents.
	"""
	if not frappe.db.exists("Page", PERMISSION_MANAGER):
		return

	current = _gate_js_hash()
	if current is None or current == _stored_gate_js_hash():
		return

	frappe.db.set_value(
		"Page", PERMISSION_MANAGER, "modified", frappe.utils.now(), update_modified=False
	)
	frappe.db.set_default(GATE_JS_HASH_KEY, current)


def _stored_gate_js_hash() -> str | None:
	"""The hash left by the last deploy that changed the script, or None.

	Read straight from the table for the reason `DEFAULTS_PARENT` gives. Written
	through `frappe.db.set_default` all the same, so the cached view every other
	reader of defaults gets stays correct.
	"""
	return frappe.db.get_value(
		"DefaultValue", {"defkey": GATE_JS_HASH_KEY, "parent": DEFAULTS_PARENT}, "defvalue"
	)


def _gate_js_hash() -> str | None:
	"""One hash over every script this app appends to that page, or None.

	The files are read back out of `page_js` rather than named here, so the two
	cannot drift: whatever `hooks.py` hands core is what gets hashed, including a
	second file somebody adds later. Resolved exactly the way
	`frappe.desk.form.meta.get_code_files_via_hooks` resolves it, because that is
	what the desk will actually serve.

	None means there is nothing to compare -- no hook, or a path that does not
	resolve to a file -- and the caller leaves the page alone rather than touching
	it on a guess.
	"""
	import hashlib

	hook = frappe.get_hooks("page_js", default={}, app_name="tbs_commons")
	files = hook.get(PERMISSION_MANAGER) or []
	if not isinstance(files, list):
		files = [files]
	if not files:
		return None

	digest = hashlib.sha256()
	for relative in files:
		path = Path(frappe.get_app_path("tbs_commons", *relative.strip("/").split("/")))
		if not path.is_file():
			return None
		# The name goes in as well as the contents, so swapping two files' paths
		# is a change even when the bytes they hold are not.
		digest.update(relative.encode())
		digest.update(path.read_bytes())
	return digest.hexdigest()
