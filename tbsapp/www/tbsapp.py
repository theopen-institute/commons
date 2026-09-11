"""Server context for the TBS App SPA page.

`tbsapp/www/tbsapp.html` is the built frontend, copied here by the Vite build.
Everything this module puts on `context.boot` is written onto `window` by the
Jinja block frappe-ui's build injects, so the SPA has a user and a CSRF token
on first paint instead of after a round trip.
"""

import frappe

no_cache = 1


def get_context(context: dict) -> dict:
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("You need to be logged in to access this page."), frappe.PermissionError)

	context.no_cache = 1
	context.boot = {
		"csrf_token": frappe.sessions.get_csrf_token(),
		"site_name": frappe.local.site,
		"user": frappe.session.user,
		"user_info": get_user_info(),
	}
	return context


def get_user_info() -> dict:
	"""The bits of the session user the sidebar renders."""
	user = frappe.get_cached_doc("User", frappe.session.user)
	return {
		"name": user.name,
		"full_name": user.full_name,
		"user_image": user.user_image,
	}
