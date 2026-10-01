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

# Whose shipped permissions shrank to System Manager in that release.
PERMISSIONS = ("Procurement Request", "Record Change Request", "Self Service Record", "Captured Document")


def run() -> None:
	keep_permissions()
	keep_mandatory_fields()
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
