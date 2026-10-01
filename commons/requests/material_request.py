"""A Material Request's links back to the Procurement Requests it orders.

`make_material_request` carries an approved request onto a Material Request and
leaves a link on the header and on every row. Those links are what a request
counts its ordered quantities by (`procurement_request.ordered_stock_qty`), so
a link that points at the wrong row, an unapproved request or another company
would quietly mark the wrong thing ordered. This checks them on every save, and
checks nothing else: what a Material Request may be for, and who may submit
one, are ERPNext's and the site's.
"""

import frappe
from frappe import _

REQUEST = "Procurement Request"


def validate_procurement_links(doc, method=None) -> None:
	"""`validate` on Material Request: every Procurement Request link is a real, approved one.

	The links are read in two queries for the whole document -- its rows'
	sources, then their requests -- rather than two per row: a Material Request
	mapped from a long Procurement Request has a row per line.
	"""
	for row in doc.items:
		if row.get("procurement_request") and not row.get("procurement_request_item"):
			frappe.throw(_("Row {0}: select the linked Procurement Request item as well.").format(row.idx))
	linked = [row for row in doc.items if row.get("procurement_request_item")]
	if not linked and not doc.get("procurement_request"):
		return

	sources = (
		{
			source.name: source
			for source in frappe.get_all(
				"Procurement Request Item",
				filters={"name": ["in", sorted({row.procurement_request_item for row in linked})]},
				fields=["name", "parent", "item_code"],
			)
		}
		if linked
		else {}
	)
	for row in linked:
		source = sources.get(row.procurement_request_item)
		if not source or source.parent != row.get("procurement_request") or source.item_code != row.item_code:
			frappe.throw(_("Row {0}: invalid Procurement Request item reference.").format(row.idx))

	requests = {source.parent for source in sources.values()}
	if doc.get("procurement_request"):
		requests.add(doc.procurement_request)
	parents = {
		parent.name: parent
		for parent in frappe.get_all(
			REQUEST,
			filters={"name": ["in", sorted(requests)]},
			fields=["name", "company", "docstatus"],
		)
	}
	for name in sorted({source.parent for source in sources.values()}):
		parent = parents.get(name)
		# `docstatus` 1 *is* the approval -- approving is what submits a request --
		# so the state it is sitting in has no say here. Asking for its name as
		# well would refuse every Material Request on a site that renamed a state,
		# and would let one through on a site that kept the name while meaning
		# something else by it.
		if not parent or parent.company != doc.company or parent.docstatus != 1:
			frappe.throw(
				_("Material Requests must refer to an approved Procurement Request in the same company.")
			)
	if doc.get("procurement_request"):
		parent = parents.get(doc.procurement_request)
		if not parent or parent.company != doc.company or parent.docstatus != 1:
			frappe.throw(_("Invalid Procurement Request reference."))
