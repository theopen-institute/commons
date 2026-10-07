"""Uninstall hook: what this app takes with it, what it leaves, and what it says.

`frappe.installer.remove_app` deletes by module. Every record whose `module`
links to one of this app's `Module Def`s is deleted, and so is every DocType in
one, with its table. Those are the modules the app brought with it
(`get_app_owned_modules`, `custom = 0`): a site's own module placed under
Commons is left alone, and so is everything in it, here as there. That sweep
is right for what this app ships and wrong in both directions for the rest,
which is what this hook is for.

Too little, on its own
----------------------
* **This app's fields on other apps' doctypes.** They carry this app's modules
  in `commons/fixtures/`, so the sweep takes the Custom Fields and Property
  Setters with it. Their database columns, and every value in them, stay:
  deleting a Custom Field never drops its column, and the sweep skips
  `on_trash` besides. Installed again, the fixtures put the same fields back
  over the same columns and the values reappear. What goes is only the field
  that would otherwise sit on a form promising behaviour nobody provides.
* **Configuration of this app's doctypes.** Frappe drops a DocType's table but
  leaves the Custom DocPerms, Property Setters, Custom Fields and Workflows
  that name it -- configuration of something that no longer exists. Removed
  here, by `drop_configuration`.
* **Derived fields.** A site's own Custom Fields, but virtual ones that only
  this app fills (`commons.derived_docfields`): without it each is a blank
  field with nothing behind it. They hold no data. Removed, and named, by
  `drop_derived_fields`.

Too much, on its own
--------------------
* **A site's own records filed under this app's modules** -- a custom DocType,
  a print format, a report. The sweep cannot tell them from what the app ships
  and would delete them, a custom DocType with its table. So the uninstall is
  refused while there are any (`refuse_while_site_records`), naming each, and
  goes ahead once they have been moved to a module of the site's own.

Said, not done
--------------
* **The permission gate.** A role ticked "Require User Permission" grants
  nothing until a User Permission narrows it. The tick is this app's field and
  goes with it, and the role then grants everything it says. That widens
  access, so it is spelt out rule by rule (`warn_gated_rules`). It does not
  stop the uninstall: removing an app is the admin's decision, and the backup
  `remove_app` took just before this hook ran holds the ticks.
* **Templates calling this app's Jinja methods** stop rendering, and no
  uninstall can repair them. Named (`warn_templates`).

Dry run
-------
`remove_app` runs `before_uninstall` on a dry run too, and passes it nothing
to tell one from the real thing. So everything here runs, and prints what it
removes; `remove_app` does not commit on a dry run, so none of it is kept.
"""

import json
import os
from collections import defaultdict

import click
import frappe

from commons.commons_core.install import APP

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(__file__)), "fixtures")

# What this app's templates may call (`jinja` in hooks.py), and where a site
# keeps Jinja that could call it: (doctype, fields).
JINJA_METHODS = ("render_web_template", "make_qr_code")
JINJA_SOURCES = (
	("Print Format", ("html",)),
	("Letter Head", ("content", "footer")),
	("Web Template", ("template", "context_prep")),
	("Email Template", ("response", "response_html")),
	("Notification", ("subject", "message")),
	("Address Template", ("template",)),
)


def before_uninstall() -> None:
	# The modules `remove_app` sweeps: the app's own, not a site's custom ones placed under it.
	modules = frappe.get_all("Module Def", filters={"app_name": APP, "custom": 0}, pluck="name")
	doctypes = frappe.get_all("DocType", filters={"module": ("in", modules)}, pluck="name") if modules else []

	# First, so a refusal leaves the site exactly as it was.
	refuse_while_site_records(modules, doctypes)

	drop_configuration(doctypes)
	drop_derived_fields()
	report_kept_columns()
	warn_gated_rules(doctypes)
	warn_templates()


def fixture_records() -> set[tuple[str, str]]:
	"""(doctype, name) of every record `commons/fixtures/` declares."""
	declared = set()
	for fname in sorted(os.listdir(FIXTURES)):
		if fname.endswith(".json"):
			with open(os.path.join(FIXTURES, fname), encoding="utf-8") as handle:
				declared |= {(row["doctype"], row["name"]) for row in json.load(handle)}
	return declared


def shipped(doctype: str, name: str, module: str) -> bool:
	"""Whether the record is one of this app's files, where the model sync reads it from."""
	from frappe.modules.utils import get_doc_path

	try:
		path = get_doc_path(module, doctype, name)
	except (ValueError, KeyError, ImportError):
		return False
	return os.path.exists(os.path.join(path, frappe.scrub(name) + ".json"))


def site_records(modules: list[str], doctypes: list[str]) -> list[tuple[str, str, str]]:
	"""(doctype, name, module) of each record the sweep would delete that this app does not ship."""
	if not modules:
		return []

	# The same map `remove_app` sweeps with, so this finds what it would delete.
	from frappe.installer import _get_module_linked_doctype_field_map

	found = [
		("DocType", row.name, row.module)
		for row in frappe.get_all(
			"DocType", filters={"module": ("in", modules), "custom": 1}, fields=["name", "module"]
		)
	]
	declared = fixture_records()
	for doctype, fieldname in _get_module_linked_doctype_field_map().items():
		# This app's own doctypes go whole, and their rows with them.
		if doctype in doctypes or doctype == "Module Def":
			continue
		meta = frappe.get_meta(doctype)
		if meta.issingle or meta.is_virtual or not frappe.db.table_exists(doctype):
			continue
		for row in frappe.get_all(doctype, filters={fieldname: ("in", modules)}, fields=["name", fieldname]):
			module = row.get(fieldname)
			if (doctype, row.name) in declared or shipped(doctype, row.name, module):
				continue
			found.append((doctype, row.name, module))
	return found


def refuse_while_site_records(modules: list[str], doctypes: list[str]) -> None:
	found = site_records(modules, doctypes)
	if not found:
		return
	lines = [f"  {doctype} {name!r} (module {module})" for doctype, name, module in found]
	raise click.ClickException(
		"Commons was not uninstalled. Uninstalling it deletes every record filed under "
		"one of its modules, and these are this site's own:\n"
		+ "\n".join(lines)
		+ "\n\nMove each to a module of this site's own -- a Module Def with Custom ticked -- "
		"and uninstall again. A custom DocType keeps its rows when its module changes. "
		"Nothing has been changed."
	)


def drop_configuration(doctypes: list[str]) -> None:
	"""What names this app's doctypes and would outlive them: their Custom DocPerms, Property Setters, Custom Fields and Workflows."""
	if not doctypes:
		return
	for doctype, field in (
		("Workflow", "document_type"),
		("Custom Field", "dt"),
		("Property Setter", "doc_type"),
		("Custom DocPerm", "parent"),
	):
		names = frappe.get_all(doctype, filters={field: ("in", doctypes)}, pluck="name")
		for name in names:
			frappe.delete_doc(doctype, name, force=True, ignore_permissions=True, ignore_missing=True)
		if names:
			print(f"Removed {len(names)} {doctype} record(s) on Commons doctypes.")


def drop_derived_fields() -> None:
	"""The site's derived fields: virtual, holding nothing, and blank without this app."""
	rows = frappe.get_all(
		"Custom Field",
		filters={"derived_from": ("is", "set")},
		fields=["name", "derived_from"],
		order_by="name",
	)
	for row in rows:
		frappe.delete_doc("Custom Field", row.name, force=True, ignore_permissions=True, ignore_missing=True)
	if rows:
		print(
			f"Removed {len(rows)} derived field(s), which only Commons fills. They held no data; "
			"the backup has their definitions:"
		)
		for row in rows:
			print(f"  {row.name} (derived from {row.derived_from})")


def report_kept_columns() -> None:
	print(
		"Commons' fields on other apps' doctypes are removed with it. Their columns and values "
		"stay in the database, and reappear if Commons is installed again."
	)


def gated_rules(doctypes: list[str]) -> dict[str, list[str]]:
	"""Ticked rules by doctype, from whichever table core reads for each, less this app's own doctypes."""
	rules = defaultdict(list)
	customised = set(frappe.get_all("Custom DocPerm", distinct=True, pluck="parent"))
	for table in ("Custom DocPerm", "DocPerm"):
		for row in frappe.get_all(
			table,
			filters={"require_user_permission": 1},
			fields=["parent", "role", "permlevel"],
			order_by="parent, role",
		):
			if row.parent in doctypes:
				continue
			# Core reads Custom DocPerm in place of DocPerm once a doctype has any.
			if table == "DocPerm" and row.parent in customised:
				continue
			level = f" (level {row.permlevel})" if row.permlevel else ""
			rules[row.parent].append(f"{row.role}{level}")
	return rules


def warn_gated_rules(doctypes: list[str]) -> None:
	from commons.safer_permissions.permissions import gate_switched_on

	rules = gated_rules(doctypes)
	if not rules:
		return

	lines = [f"  {doctype}: {', '.join(roles)}" for doctype, roles in sorted(rules.items())]
	if not gate_switched_on():
		click.secho(
			"Note: these Role Permissions are ticked Require User Permission, but the gate is "
			"switched off in Commons Settings, so they already grant their full access. Removing "
			"Commons removes the ticks and changes nothing else:\n" + "\n".join(lines),
			fg="yellow",
		)
		return

	click.secho(
		"WARNING: removing Commons removes the permission gate, and access widens.\n\n"
		"These Role Permissions are ticked Require User Permission. Today each grants nothing "
		"until a User Permission for that doctype narrows it. Once Commons is gone, the tick is "
		"gone with it and each role grants everything it says:\n"
		+ "\n".join(lines)
		+ "\n\nWhat changes for someone holding one of these roles:\n"
		"  * With no User Permission for the doctype, they see every record of it, where today they see none.\n"
		"  * A User Permission that applies to all doctypes now narrows them; the gate ignored those.\n"
		"  * Query and Script Reports on the doctype, which run their own SQL and ignore User\n"
		"    Permissions, open to them; today they are refused.\n"
		"  * A User Permission for the doctype narrows them as before.\n\n"
		"To keep the restriction without Commons, give each such user a User Permission for the "
		"doctype, or take the role away from whoever should not see all of it. The backup taken "
		"before this uninstall holds the ticks.",
		fg="yellow",
		bold=True,
	)


def warn_templates() -> None:
	found = []
	for doctype, fields in JINJA_SOURCES:
		if not frappe.db.table_exists(doctype):
			continue
		for field in fields:
			if not frappe.db.has_column(doctype, field):
				continue
			for method in JINJA_METHODS:
				for name in frappe.get_all(doctype, filters={field: ("like", f"%{method}%")}, pluck="name"):
					found.append(f"  {doctype} {name!r} calls {method}")
	if found:
		click.secho(
			"These templates call Commons' Jinja methods and will fail to render once it is gone:\n"
			+ "\n".join(sorted(set(found))),
			fg="yellow",
		)
