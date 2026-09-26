"""What a form asks when one of its links changes.

The form loads with its derived values (the document half puts them in
`as_dict`), but a link changed on screen isn't saved yet, so the new value has
to be looked up for it. The form sends the record as it stands; this builds an
unsaved document from it and reads the derived fields off that -- the same
lookup a saved record gets, so a field shows the same thing before and after
the save.

Asked of someone who can write the record (or create one, for a new record),
not merely read it: whoever can save a link could see what it leads to by
saving it anyway, while a reader who can't would otherwise have a way to look
up any linked record by naming it. The derived fields' own permlevels still
apply.

That reasoning holds link by link, not only for the record as a whole. A user
who may save a Faculty but not its `member` -- a link above their permlevel,
read-only, set only once, or on a submitted record -- can't point it at
somebody else by saving, so they can't by asking either: for each field a
derived path starts from on the host, a value they couldn't have saved is
replaced by the one saving would have kept (`unwritable`).
"""

import frappe
from frappe import _

from commons.derived_docfields import registry
from commons.derived_docfields.document import sources_on_host
from commons.derived_docfields.registry import BrokenPath


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
	# What saving would keep of a field the user can't write: the stored value,
	# or the default on a new record -- as core's `reset_values_if_no_permlevel_access`.
	kept = frappe.get_doc(doctype, name) if saved else frappe.new_doc(doctype)
	for fieldname in unwritable(record, sources(doctype, active), kept, saved):
		record.set(fieldname, kept.get(fieldname))

	permitted = record.permitted_fieldnames
	return {fieldname: record.get(fieldname) for fieldname in active if fieldname in permitted}


def sources(doctype: str, active: dict) -> set[str]:
	"""The host fields the derived fields' paths start from: links, and Dynamic Link types."""
	plans = []
	for fieldname in active:
		try:
			plans.append(registry.plan(doctype, fieldname))
		except BrokenPath:
			# Reads as empty whatever is sent; the document half reports it.
			continue
	return sources_on_host(plans)


def unwritable(record, fieldnames, kept, saved: bool) -> list[str]:
	"""Which of `fieldnames` the user could not set on `record` by saving it.

	Judged against `kept`, the record as stored (or as a new one starts), never
	against what was sent: a form can claim any `docstatus`. Read Only counts,
	though core doesn't enforce it on save, because nobody using the form can
	enter one; a Read Only link filled by Fetch From shows its stored value
	here until the record is saved, which errs the safe way. Administrator
	writes at every permlevel, as core's `validate_higher_perm_levels` has it.
	"""
	meta = record.meta
	administrator = frappe.session.user == "Administrator"
	writable_levels = meta.get_permlevel_access("write", parenttype=record.get("parenttype"))
	found = []
	for fieldname in fieldnames:
		df = meta.get_field(fieldname)
		if df is None or df.read_only:
			found.append(fieldname)
		elif not administrator and df.permlevel not in writable_levels:
			found.append(fieldname)
		elif saved and df.set_only_once:
			found.append(fieldname)
		elif saved and kept.docstatus != 0 and not (kept.docstatus == 1 and df.allow_on_submit):
			found.append(fieldname)
	return found
