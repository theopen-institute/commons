"""Which doctypes Data Sync compares, which records of each, and how a record is
recognised on the other site.

A rule is a plain dict -- `doctype`, `filters`, `key_fields`, `ignored_fields` --
because it travels: the page reads this site's rules, sends them to the source
site with every request, and both sides load and hash records by the same rule.
Hashes from two sites only agree when both used the same filters, the same key
and the same ignored fields, so the rule is never read from the source's own
settings.

The rows live on the Data Sync tab of Commons Settings. An empty table means
`DEFAULT_RULES`, so a site gets a sensible list without saving anything; the
tab's "Fill With Defaults" button copies them in to start editing from. Order
matters: it is the order the page lists doctypes in, and the order to copy
changes in -- a Property Setter cannot land before the Custom Field it changes.
"""

import json

import frappe
from frappe import _

SETTINGS = "Commons Settings"
TABLE = "Data Sync Doctype"

# Site-made customisation, in the order it depends on itself. App-shipped
# records (standard reports, print formats, workspaces and sidebars) are left
# out: they arrive with the app and its migrate, not through this.
#
# The navigation (Frappe 16.50's): a custom Module Def is a module the site made,
# and comes first, since custom doctypes, workspaces and sidebars name it. A
# workspace is site-made when it is not `standard` -- every workspace has a
# module since 16.50, so a module is no longer the sign. A site's `Sidebar` is
# not `standard` either. `Custom Sidebar` (a module's sidebar as the site edits
# it) and the site's `Dock` arrangements are named by a hash, different on every
# site, so they are recognised by what they are for: the module or the app, and
# no user -- each person's own layer stays theirs. Navigation Apps come last:
# their rows name modules.
DEFAULT_RULES = [
	{"doctype": "Module Def", "filters": {"custom": 1}},
	{"doctype": "DocType", "filters": {"custom": 1}, "ignored_fields": ["migration_hash"]},
	{"doctype": "Custom Field"},
	{"doctype": "Property Setter"},
	{"doctype": "Custom DocPerm", "key_fields": ["parent", "role", "permlevel", "if_owner"]},
	{"doctype": "Workflow State"},
	{"doctype": "Workflow Action Master"},
	{"doctype": "Workflow"},
	{"doctype": "Client Script"},
	{"doctype": "Server Script"},
	{"doctype": "Report", "filters": {"is_standard": "No"}},
	{"doctype": "Print Format", "filters": {"standard": "No"}},
	{"doctype": "Web Template", "filters": {"standard": 0}},
	{"doctype": "Email Template"},
	{"doctype": "Notification", "filters": {"is_standard": 0}},
	{"doctype": "Dashboard Chart", "filters": {"is_standard": 0}, "ignored_fields": ["last_synced_on"]},
	{"doctype": "Number Card", "filters": {"is_standard": 0}},
	{"doctype": "Workspace", "filters": {"standard": 0, "for_user": ["is", "not set"]}},
	{"doctype": "Sidebar", "filters": {"standard": 0}},
	{"doctype": "Custom Sidebar", "filters": {"user": ["is", "not set"]}, "key_fields": ["module", "user"]},
	{
		"doctype": "Dock",
		"filters": {"standard": 0, "user": ["is", "not set"]},
		"key_fields": ["app", "user"],
	},
	{"doctype": "Navigation App"},
]


def configured() -> list[dict]:
	"""This site's rules: the settings table, or the defaults when it is empty.

	Also answers between this code landing and the migrate that creates the table.
	"""
	rows = []
	if frappe.db.table_exists(TABLE):
		rows = frappe.get_all(
			TABLE,
			filters={"parenttype": SETTINGS, "parentfield": "data_sync_doctypes"},
			fields=["document_type", "filters", "key_fields", "ignored_fields"],
			order_by="idx asc",
		)
	if not rows:
		return [normalise(rule) for rule in DEFAULT_RULES]
	return [
		normalise(
			{
				"doctype": row.document_type,
				"filters": row.filters,
				"key_fields": row.key_fields,
				"ignored_fields": row.ignored_fields,
			}
		)
		for row in rows
	]


def source_url() -> str:
	if not frappe.db.table_exists(TABLE):
		return ""
	return (frappe.db.get_single_value(SETTINGS, "data_sync_source_url") or "").strip().rstrip("/")


def parse(rules) -> list[dict]:
	"""Rules as a request carries them (JSON text or a list), checked."""
	if isinstance(rules, str):
		rules = json.loads(rules)
	if isinstance(rules, dict):
		rules = [rules]
	return [normalise(rule) for rule in rules or []]


def normalise(rule: dict) -> dict:
	"""One rule with every key present and every value in its one shape.

	Filters arrive as JSON text from the settings table and as objects from a
	request; key and ignored fields as comma lists or as lists. Settling them here
	means the hash on each side is computed from the same thing.
	"""
	doctype = (rule.get("doctype") or "").strip()
	if not doctype:
		frappe.throw(_("A Data Sync rule names no doctype."))

	filters = rule.get("filters") or None
	if isinstance(filters, str):
		try:
			filters = json.loads(filters) if filters.strip() else None
		except ValueError:
			frappe.throw(_("The filters for {0} are not valid JSON.").format(doctype))
	if filters is not None and not isinstance(filters, dict | list):
		frappe.throw(_("The filters for {0} must be a JSON object or list.").format(doctype))

	return {
		"doctype": doctype,
		"filters": filters or None,
		"key_fields": _names(rule.get("key_fields")),
		"ignored_fields": _names(rule.get("ignored_fields")),
	}


def _names(value) -> list[str]:
	if not value:
		return []
	if isinstance(value, str):
		value = value.replace("\n", ",").split(",")
	return [name.strip() for name in value if name and name.strip()]


@frappe.whitelist()
def defaults() -> list[dict]:
	"""The default rules as settings rows, for the tab's "Fill With Defaults"."""
	frappe.only_for("System Manager")
	return [
		{
			"document_type": rule["doctype"],
			"filters": json.dumps(rule["filters"]) if rule["filters"] else "",
			"key_fields": ", ".join(rule["key_fields"]),
			"ignored_fields": ", ".join(rule["ignored_fields"]),
		}
		for rule in map(normalise, DEFAULT_RULES)
	]
