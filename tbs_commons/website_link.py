# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Where the "Website" button goes -- and only that button.

The desk sidebar's "Website" entry and this app's own sidebar both open the site
root, `/`. Frappe resolves `/` through `frappe.website.utils.get_home_page`: the
first `home_page` on any of the user's Roles, else Portal Settings'
`default_portal_home`, else a `home_page` hook, else Website Settings' `home_page`
-- and that same function is what `frappe.auth` redirects a fresh login to. So the
button and the landing page are one setting, and there is no way to move the
button without moving where people arrive when they log in.

This module adds the second setting the cascade never had: a Website Settings
field holding an arbitrary URL for the button alone. Login is untouched, because
nothing here is read by `get_home_page` -- it is read by the two sidebars and
nowhere else. Left empty, both buttons keep opening the site root exactly as
before.
"""

import frappe

FIELDNAME = "website_button_url"

LABEL = "Website Button Target"

DESCRIPTION = (
	"Where the <b>Website</b> button in the desk sidebar and the TBS Commons sidebar opens. "
	"An absolute URL (<code>https://example.org</code>) or a path on this site "
	"(<code>/about</code>). Leave blank to open the site root. "
	"This does <b>not</b> change where anyone lands after logging in &mdash; that is Home Page above, "
	"together with the Home Page on each Role."
)


def sync_website_button_field() -> None:
	"""Create the field on install and migrate. Safe to run repeatedly.

	A Custom Field rather than a fork of Website Settings: the target of a button
	is site configuration, and carrying a patched core doctype to say so would
	mean re-patching it on every Frappe release.
	"""
	from frappe.custom.doctype.custom_field.custom_field import create_custom_field

	properties = {
		"fieldname": FIELDNAME,
		"label": LABEL,
		"fieldtype": "Data",
		"options": "URL",
		"description": DESCRIPTION,
		# Beside Home Page, in the same column, so the pair reads as the two
		# halves of a decision that used to be one field.
		"insert_after": "home_page",
	}

	existing = frappe.db.get_value("Custom Field", {"dt": "Website Settings", "fieldname": FIELDNAME})
	if existing:
		# The label and description are the whole of this field's UI, and the
		# distinction they draw is the point of it -- so a site that already has
		# the field gets the current wording on migrate rather than whichever
		# wording it was installed with.
		field = frappe.get_doc("Custom Field", existing)
		field.update(properties)
		field.save(ignore_permissions=True)
		return

	create_custom_field("Website Settings", properties)


def get_website_button_url() -> str:
	"""The configured target, or "" for "open the site root".

	Empty rather than `window.location.origin` filled in here: the origin the
	browser is on is the browser's to know, and a server-rendered one is wrong the
	moment the site answers on a second hostname.

	Website Settings is a Single, so the field is a row in `tabSingles` rather than
	a column -- between this app being installed and its first migrate there is
	simply no row, and this reads as unset without a guard.
	"""
	return (frappe.db.get_single_value("Website Settings", FIELDNAME) or "").strip()


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Hand the desk the target, so its sidebar does not have to ask for it."""
	bootinfo[FIELDNAME] = get_website_button_url()
