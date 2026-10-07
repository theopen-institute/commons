# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Where the "Website" button goes -- and only that button.

This app's own sidebar has a "Website" entry, and it opens the site root, `/`.
Frappe resolves `/` through `frappe.website.utils.get_home_page`: the first
`home_page` on any of the user's Roles, else Portal Settings'
`default_portal_home`, else a `home_page` hook, else Website Settings'
`home_page` -- and that same function is what `frappe.auth` redirects a fresh login to. So the
button and the landing page are one setting, and there is no way to move the
button without moving where people arrive when they log in.

This module adds the second setting the cascade never had: a Website Settings
field holding an arbitrary URL for the button alone. Login is untouched, because
nothing here is read by `get_home_page` -- it is read by this app's sidebar and
nowhere else. Left empty, the button keeps opening the site root exactly as
before. (The desk had a Website entry too until Frappe 16.50 dropped it.)

This app's sidebar reads the value from boot data in a production build (put
there by `www/commons.py`) and from the endpoint below in the dev server. The
desk has no Website entry, so the desk boot does not carry it.

Not to be confused with [home_page.py] next door, which is where people *land*.
That is the other half of the cascade this separates.
"""

import frappe

FIELDNAME = "website_button_url"


@frappe.whitelist()
def get_website_button_url() -> str:
	"""The configured target, or "" for "open the site root".

	Empty rather than `window.location.origin` filled in here: the origin the
	browser is on is the browser's to know, and a server-rendered one is wrong the
	moment the site answers on a second hostname.

	Whitelisted as well as read internally, and it is the same answer either way:
	a production SPA build gets it through the page's boot data, but the Vite dev
	server serves `index.html` without the Jinja pass, so the SPA asks for it. A setting whose whole content
	is "where a button on this page goes" tells a logged-in user nothing they
	could not read off the button.

	Website Settings is a Single, so the field is a row in `tabSingles` rather than
	a column -- between this app being installed and its first migrate there is
	simply no row, and this reads as unset without a guard.
	"""
	return (frappe.db.get_single_value("Website Settings", FIELDNAME) or "").strip()
