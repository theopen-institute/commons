"""What a form asks when one of its links changes.

The form loads with its derived values (the document half puts them in
`as_dict`), but a link changed on screen isn't saved yet, so the new value has
to be looked up for it. The form sends the record as it stands; this builds an
unsaved document from it and reads the derived fields off that -- the same
lookup a saved record gets, so a field shows the same thing before and after
the save.

Asked of someone who can write the record (or create one, for a new record),
not merely read it: whoever can save the link could see what it leads to by
saving it anyway, while a reader who can't would otherwise have a way to look
up any linked record by naming it. The derived fields' own permlevels still
apply.
"""

import frappe
from frappe import _

from commons.derived_docfields import registry


@frappe.whitelist(methods=["POST"])
def resolve(doc: str | dict) -> dict:
	"""The derived values of `doc` -- a form's record, saved or not -- as its links stand now."""
	values = frappe.parse_json(doc) or {}
	if not isinstance(values, dict) or not isinstance(values.get("doctype"), str):
		frappe.throw(_("A document is required."))

	doctype = values["doctype"]
	active = registry.active_for(doctype)
	if not active:
		return {}

	name = values.get("name")
	saved = bool(name) and not values.get("__islocal") and frappe.db.exists(doctype, name)
	if not (
		frappe.has_permission(doctype, "write", doc=name)
		if saved
		else frappe.has_permission(doctype, "create")
	):
		frappe.throw(_("Not permitted"), frappe.PermissionError)

	record = frappe.get_doc(values)
	permitted = record.permitted_fieldnames
	return {fieldname: record.get(fieldname) for fieldname in active if fieldname in permitted}
