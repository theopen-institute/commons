# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Stand-ins for Frappe endpoints that are broken upstream, each to be deleted once Frappe
fixes its own.

Each is reached through `override_whitelisted_methods` in `hooks.py`, does the one thing
the broken endpoint gets wrong, and hands everything else to Frappe's own function
unchanged -- so the behaviour is Frappe's, and taking the line out of `hooks.py` is all
it takes to go back to it.

`save_page` (Frappe 16.50, still so on version-16 and develop as of 2026-10-07)
-----------------------------------------------------------------------------
Saving a workspace in the desk's editor fails with "Argument 'new_widgets' ... should be
of type 'dict' but got 'str'". The editor passes `new_widgets` to `frappe.call` as an
object, and `frappe.call` sends every object as JSON text; `save_page` was then
annotated `new_widgets: dict` (98d4a6c0a9, "allow new_widgets to be a dict"), and the
type check that runs before the function rejects the text. So no workspace can be saved
from the editor. This accepts the text too, reads it back into a dict, and calls Frappe's
`save_page`. Delete it, and its hook line, when Frappe's endpoint accepts the text again.
"""

import frappe


@frappe.whitelist()
def save_page(name: str, public: str | int, new_widgets: dict | str, blocks: str):
	from frappe.desk.doctype.workspace.workspace import save_page as frappe_save_page

	return frappe_save_page(
		name=name,
		public=public,
		new_widgets=(frappe.parse_json(new_widgets) if new_widgets else None) or {},
		blocks=blocks,
	)
