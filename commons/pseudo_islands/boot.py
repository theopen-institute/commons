"""The boot half of desk islands on Frappe v16.

frappe develop adds `bootinfo.ui_islands` in `frappe.sessions.get_bootinfo`, the
list the desk loader resolves an island's name against. v16 sends
`assets_json` already and not the list, so this adds it, where Commons Settings
switches desk islands on.

It steps aside for a Frappe that fills the list itself, so it is safe on v17
before this module is deleted. See `commons/pseudo_islands/README.md`.
"""

import frappe

from commons.commons_core.settings import ENABLE_PSEUDO_ISLANDS, feature_enabled


def enabled() -> bool:
	return feature_enabled(ENABLE_PSEUDO_ISLANDS)


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	if "ui_islands" in bootinfo or not enabled():
		return

	from commons.pseudo_islands.registry import get_ui_islands

	bootinfo.ui_islands = get_ui_islands()
