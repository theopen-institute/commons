"""Install and migrate hook for the requests section: the fields it adds to ERPNext.

Four Custom Fields, on `Material Request` and `Material Request Item`. They are
what ties a Material Request back to the Procurement Request it came from -- see
`commons.requests.budget`, which counts a department's spend from them -- and
they are the only part of this app that writes onto a doctype another app owns.

They used to ship in `commons/fixtures/custom_field.json` with the four this app
adds to core, and Frappe's own fixture sync wrote all eight. That worked and
needed no hook, which was the argument for it. It stopped working the moment
ERPNext became optional, and it failed in a way worth writing down, because
nothing about the failure points at this app:

* a Custom Field naming a doctype that is not on the site raises
  `LinkValidationError`;
* `frappe.utils.fixtures.import_fixtures` has a guard for exactly this case, but
  it catches `ImportError` and `DoesNotExistError` only, so that one escapes;
* it escapes into `SiteMigration.post_schema_updates`, which is `@atomic` -- and
  that decorator rolls back and re-raises;
* so migrate aborts partway through the post-schema phase. Fixtures and job
  syncing for the whole *site* are rolled back, everything ordered after
  fixtures is skipped, and no app's `after_migrate` hooks run at all.

One unresolvable field in one app therefore breaks migrate for every app on the
site. Asserting these four from a guarded hook instead is what ERPNext and HRMS
do for their own cross-app fields, and it is the only shape that can say "not on
this site, so not now".

The other four stay fixtures. They name `Website Settings`, `Role`,
`Custom DocPerm` and `DocPerm`, which are Frappe's own and are never absent, so
nothing is gained by moving them and the declaration is better off where Frappe
can read it.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MATERIAL_REQUEST = "Material Request"
MATERIAL_REQUEST_ITEM = "Material Request Item"

# Verbatim what the fixture held, minus the bookkeeping Frappe fills in itself:
# `name` is derived from `dt` and `fieldname`, `owner` is set to Administrator by
# `create_custom_field`, and `is_system_generated` is its default. A site that
# already has these from the old fixture is matched on (`dt`, `fieldname`) and
# updated in place rather than duplicated.
PROCUREMENT_CUSTOM_FIELDS = {
	MATERIAL_REQUEST: [
		{
			"fieldname": "procurement_request",
			"label": "Procurement Request",
			"fieldtype": "Link",
			"options": "Procurement Request",
			"insert_after": "job_card",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
		},
		{
			"fieldname": "department",
			"label": "Department",
			"fieldtype": "Link",
			"options": "Department",
			"insert_after": "company",
			"search_index": 1,
			"description": (
				"Whose budget this request is charged to. Required to submit Purchase/Material "
				"Issue requests; inherited from linked Procurement Requests."
			),
		},
	],
	MATERIAL_REQUEST_ITEM: [
		{
			"fieldname": "procurement_request",
			"label": "Procurement Request",
			"fieldtype": "Link",
			"options": "Procurement Request",
			"insert_after": "job_card_item",
			"read_only": 1,
			"no_copy": 1,
			"print_hide": 1,
			"search_index": 1,
		},
		{
			"fieldname": "procurement_request_item",
			"label": "Procurement Request Item",
			"fieldtype": "Data",
			"insert_after": "procurement_request",
			"read_only": 1,
			"hidden": 1,
			"no_copy": 1,
			"print_hide": 1,
			"search_index": 1,
		},
	],
}


def sync_procurement_custom_fields() -> None:
	"""Write the four fields, on a site that has the doctypes to write them onto.

	Silent on a site that does not. That is not a degraded install: without
	ERPNext there are no Material Requests to tie back to anything, the
	procurement section takes itself off the navigation, and the fields would
	have nothing to describe -- see `approvals.RequestType.available`.

	Both doctypes are tested rather than one. They come from the same app and in
	practice arrive together, but `create_custom_fields` is given both in one
	call and a half-answer here would be a half-applied one there.
	"""
	if not all(
		frappe.db.exists("DocType", doctype, cache=True)
		for doctype in (MATERIAL_REQUEST, MATERIAL_REQUEST_ITEM)
	):
		return

	create_custom_fields(PROCUREMENT_CUSTOM_FIELDS)
