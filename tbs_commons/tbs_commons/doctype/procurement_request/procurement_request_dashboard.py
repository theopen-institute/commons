# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

from frappe import _


def get_data() -> dict:
	"""Connections tab: the stock documents this request turned into.

	`procurement_request` is a Custom Field this app adds to Material Request --
	see `tbsapp.install`.
	"""
	return {
		"fieldname": "procurement_request",
		"transactions": [
			{"label": _("Procurement"), "items": ["Material Request"]},
		],
	}
