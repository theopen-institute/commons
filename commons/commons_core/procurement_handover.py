"""Hand Department Budget to the sites that hold budgets, and keep each site's permissions.

TEMPORARY. Delete this file, and its entry in `before_migrate`, once every site
carrying this app has migrated past the release that removed
`commons/requests/doctype/department_budget/` and shrank the shipped
permissions below. Nothing else calls it.

That release took this app's procurement process out of it. Procurement
Request stays, as a doctype a site's own Workflow drives; what went is what
the app had decided on the site's behalf -- an annual allocation per
department, enforced when a request is approved and when a Material Request is
submitted, and the roles that may raise, code, approve and see requests.

What happens, per site
----------------------
* **Department Budget, where the site has budgets** (tbs): the doctype becomes
  the site's own -- a custom doctype in a custom `Department Budgets` module,
  rows untouched, with the same fields, properties and permissions, checked by
  `community_handover`'s before-and-after snapshot. What it loses is its
  controller, and with it every rule it carried: dates taken from the fiscal
  year, one submitted allocation per department and period, an amount no lower
  than what is charged. Nothing is charged any more, either; a site that wants
  budgets enforced writes that as a Server Script. `Material Request.department`,
  which this app shipped for the budget, stays as the site's field.
* **Department Budget, where it has none**: nothing here. Frappe's orphan
  cleanup removes the definition, and `Material Request.department` goes too
  when no Material Request has a value in it.
* **Shipped permissions** of Procurement Request, Record Change Request, Self
  Service Record and Captured Document are now System Manager only, so a new
  site grants the rest in the Role Permission Manager. A site that already ran
  them keeps exactly what it had: the old rows become its Custom DocPerms
  (`frappe.permissions.setup_custom_perms`), which Frappe reads in place of
  the shipped ones. A site that had customised them already is left alone.
* **Procurement Request's department and approver** were mandatory and now are
  not. A site that has requests, or a Workflow for them, keeps them mandatory
  through a Property Setter each.
* **Buyers verifying rates**: `Procurement Request Item.verified_rate` and
  `Procurement Request.rejection_reason` (now labelled Review Note) shipped at
  permlevel 1 and now ship at 0. A site whose stored fields are still at 1
  keeps them there through a `permlevel` Property Setter each -- and so keeps
  whatever its permlevel-1 rights said about who may write them.
* **Unassigned expense claims**: deciding a claim that names no approver, by
  anyone who may submit claims, became Commons Settings'
  `expense_unassigned_open`, off by default as in HRMS. A site with HRMS that
  ran this app before the setting existed, and has never stored it, gets it on.
* **The other new request settings** -- the change request outcome that
  applies a change, whether a reviewer may decide their own, and what the
  procurement queue is grouped by -- are stored at their defaults wherever a
  site has never stored them. A Single loads a field it has no row for as
  blank, or 0, so the form would otherwise show them unset, and the next save
  of it for any other reason would write that over what the site was doing.

Why `before_migrate`: the same reason as `community_handover` -- after the
files are gone and before the doctype sync (which would write the shrunk
permissions and the relaxed fields over the old ones) and the orphan cleanup
(which would delete Department Budget) act on their absence.
"""

import frappe

from commons.commons_core import community_handover

BUDGET = "Department Budget"
BUDGET_MODULE = "Department Budgets"
APP_MODULE = "Requests"
BUDGET_FIELD = "Material Request-department"

REQUEST = "Procurement Request"
MANDATORY = ("department", "approver")

# Shipped at permlevel 1, now at 0: (doctype, fieldname).
RAISED_FIELDS = (("Procurement Request Item", "verified_rate"), (REQUEST, "rejection_reason"))

SETTINGS = "Commons Settings"
EXPENSE_CLAIM = "Expense Claim"
UNASSIGNED_OPEN = "expense_unassigned_open"

# Whose shipped permissions shrank to System Manager in that release.
PERMISSIONS = ("Procurement Request", "Record Change Request", "Self Service Record", "Captured Document")


def run() -> None:
	keep_permissions()
	keep_mandatory_fields()
	keep_raised_permlevels()
	keep_unassigned_expense_claims_open()
	store_setting_defaults()
	hand_over_budgets()


def keep_permissions() -> None:
	"""The rows each site ran with, as its own Custom DocPerms, before the sync shrinks them."""
	from frappe.permissions import setup_custom_perms

	for doctype in PERMISSIONS:
		if not frappe.db.exists("DocType", {"name": doctype, "custom": 0}):
			continue
		# Only while the stored rows are still the old ones: once a migrate has
		# synced System Manager alone, there is nothing left to keep.
		if not frappe.db.exists("DocPerm", {"parent": doctype, "role": ("!=", "System Manager")}):
			continue
		if setup_custom_perms(doctype):
			frappe.clear_cache(doctype=doctype)
			print(f"Procurement handover: {doctype} keeps this site's permissions as Custom DocPerms.")


def keep_mandatory_fields() -> None:
	"""Department and approver stay mandatory where requests are already being made."""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	if not frappe.db.exists("DocType", {"name": REQUEST, "custom": 0}):
		return
	in_use = frappe.db.count(REQUEST) or frappe.db.exists("Workflow", {"document_type": REQUEST})
	if not in_use:
		return
	for fieldname in MANDATORY:
		# Still mandatory in the stored DocField means the sync has not yet run.
		if not frappe.db.get_value("DocField", {"parent": REQUEST, "fieldname": fieldname}, "reqd"):
			continue
		if frappe.db.exists(
			"Property Setter", {"doc_type": REQUEST, "field_name": fieldname, "property": "reqd"}
		):
			continue
		make_property_setter(
			REQUEST,
			fieldname,
			"reqd",
			"1",
			"Check",
			validate_fields_for_doctype=False,
			is_system_generated=False,
		)
		print(f"Procurement handover: {REQUEST}.{fieldname} stays mandatory on this site.")


def keep_raised_permlevels() -> None:
	"""Fields that shipped at permlevel 1 stay there where the site ran them so.

	The same shape as `keep_mandatory_fields`: the stored DocField still at 1
	means the sync that lowers it has not run, and a Property Setter already
	there is the site's own say, left alone.
	"""
	from frappe.custom.doctype.property_setter.property_setter import make_property_setter

	for doctype, fieldname in RAISED_FIELDS:
		if not frappe.db.exists("DocType", {"name": doctype, "custom": 0}):
			continue
		if frappe.db.get_value("DocField", {"parent": doctype, "fieldname": fieldname}, "permlevel") != 1:
			continue
		if frappe.db.exists(
			"Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": "permlevel"}
		):
			continue
		make_property_setter(
			doctype,
			fieldname,
			"permlevel",
			"1",
			"Int",
			validate_fields_for_doctype=False,
			is_system_generated=False,
		)
		print(f"Procurement handover: {doctype}.{fieldname} stays at permlevel 1 on this site.")


def setting_stored(fieldname: str) -> bool:
	"""Whether `tabSingles` has a row for this Commons Settings field, whatever its value.

	A query of its own because neither `frappe.db.exists` nor `get_value` reads
	`Singles` as a table: both treat it as a doctype and order by a column it
	does not have.
	"""
	singles = frappe.qb.DocType("Singles")
	return bool(
		frappe.qb.from_(singles)
		.select(singles.field)
		.where((singles.doctype == SETTINGS) & (singles.field == fieldname))
		.limit(1)
		.run()
	)


def keep_unassigned_expense_claims_open() -> None:
	"""A claim naming no approver stays anyone's to decide where it always was.

	Only where HRMS's Expense Claim is here, and only while the setting has
	never been stored: once a site has ticked or unticked it, that is its
	answer. And only on a site that ran this app before the setting existed --
	the setting's DocField not synced yet, or claims already raised. A new site
	that merely migrates again has neither, and keeps HRMS's default.
	"""
	if not frappe.db.exists("DocType", EXPENSE_CLAIM) or not frappe.db.exists("DocType", SETTINGS):
		return
	if setting_stored(UNASSIGNED_OPEN):
		return
	synced = frappe.db.exists("DocField", {"parent": SETTINGS, "fieldname": UNASSIGNED_OPEN})
	if synced and not frappe.db.count(EXPENSE_CLAIM):
		return
	frappe.db.set_single_value(SETTINGS, UNASSIGNED_OPEN, 1, update_modified=False)
	print("Procurement handover: expense claims naming no approver stay open to any approver on this site.")


def store_setting_defaults() -> None:
	"""Each new request setting at its default, wherever a site has never stored it.

	The defaults are the ones the readers fall back to, named where they are
	read, so this cannot store something other than what the site was already
	getting.
	"""
	from commons.requests.procurement import DEFAULT_GROUP_BY, GROUP_BY_SETTING
	from commons.self_service.doctype.record_change_request.record_change_request import (
		APPLYING_OUTCOME_SETTING,
		DEFAULT_APPLYING_OUTCOME,
		SELF_APPROVAL_SETTING,
	)

	if not frappe.db.exists("DocType", SETTINGS):
		return
	defaults = {
		APPLYING_OUTCOME_SETTING: DEFAULT_APPLYING_OUTCOME,
		SELF_APPROVAL_SETTING: 1,
		GROUP_BY_SETTING: DEFAULT_GROUP_BY,
	}
	missing = {field: value for field, value in defaults.items() if not setting_stored(field)}
	if not missing:
		return
	frappe.db.set_single_value(SETTINGS, missing, update_modified=False)
	print(f"Procurement handover: stored the defaults of {', '.join(sorted(missing))} in {SETTINGS}.")


def hand_over_budgets() -> None:
	row = frappe.db.get_value("DocType", BUDGET, ("custom", "module"), as_dict=True)
	if not row or row.custom or row.module != APP_MODULE:
		return
	if not frappe.db.count(BUDGET):
		drop_budget_field()
		return

	before = community_handover.snapshot(BUDGET)

	if not frappe.db.exists("Module Def", BUDGET_MODULE):
		module = frappe.get_doc({"doctype": "Module Def", "module_name": BUDGET_MODULE, "custom": 1})
		# A custom module names no app, which the field's own `reqd` does not know.
		module.flags.ignore_mandatory = True
		module.insert(ignore_permissions=True)
	frappe.db.set_value("DocType", BUDGET, "module", BUDGET_MODULE, update_modified=False)
	frappe.db.set_value("Custom Field", BUDGET_FIELD, "module", BUDGET_MODULE, update_modified=False)
	community_handover.convert(BUDGET)

	frappe.clear_cache()
	after = community_handover.snapshot(BUDGET)
	# Moving it is the point, so the module is expected to change. So are the
	# list view's columns, where it had none: a custom doctype's save picks its
	# mandatory fields for them (`DocType.set_default_in_list_view`).
	before["doctype"]["module"] = after["doctype"]["module"]
	if not any(props.get("in_list_view") for _, props in before["fields"]):
		chosen = {name: props.get("in_list_view") for name, props in after["fields"]}
		for name, props in before["fields"]:
			props["in_list_view"] = chosen.get(name)
	differences = community_handover.compare(before, after)
	if differences:
		frappe.throw(
			"Procurement handover changed what Department Budget is:\n" + "\n".join(differences),
			title="Procurement handover",
		)
	print(f"Procurement handover: {BUDGET} is this site's own doctype now, in {BUDGET_MODULE}.")


def drop_budget_field() -> None:
	"""`Material Request.department`, where nothing has ever been budgeted by it."""
	if not frappe.db.exists("Custom Field", BUDGET_FIELD):
		return
	if frappe.db.has_column("Material Request", "department") and frappe.db.exists(
		"Material Request", {"department": ("is", "set")}
	):
		return
	frappe.delete_doc("Custom Field", BUDGET_FIELD, ignore_permissions=True)
	print("Procurement handover: removed Material Request's unused department field.")
