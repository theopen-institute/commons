"""Server context for the Commons SPA page.

`commons/www/commons.html` is the built frontend, copied here by the Vite build.
Everything this module puts on `context.boot` is written onto `window` by the
Jinja block frappe-ui's build injects, so the SPA has a user and a CSRF token
on first paint instead of after a round trip.
"""

import hashlib

import frappe

no_cache = 1


def get_context(context: dict) -> dict:
	if frappe.session.user == "Guest":
		frappe.throw(frappe._("You need to be logged in to access this page."), frappe.PermissionError)

	from commons.core.website_link import get_website_button_url
	from commons.shell.api import get_shell

	context.no_cache = 1
	context.boot = {
		"csrf_token": frappe.sessions.get_csrf_token(),
		"site_name": frappe.local.site,
		"user": frappe.session.user,
		"user_info": get_user_info(),
		"website_button_url": get_website_button_url(),
		# What the app is called and what is in its sidebar, so the first paint
		# is the real sidebar rather than a frame waiting for one. The endpoint
		# behind it stays whitelisted for the dev server -- see
		# `commons.shell.api`.
		"shell": get_shell(),
	}
	return context


# The desk's avatar palette, in its order, from
# frappe/public/js/frappe/utils/common.js. `get_palette` indexes it modulo 8, so
# the ninth entry is only ever the no-name fallback.
AVATAR_PALETTE = (
	"orange",
	"pink",
	"blue",
	"green",
	"dark-green",
	"red",
	"yellow",
	"purple",
	"gray",
)


def get_avatar_color(full_name: str) -> str:
	"""The colour the desk gives this person's avatar.

	The same arithmetic `frappe.get_palette` does in the desk, over the same
	string, so one person is one colour in both places -- which is the whole
	point of an avatar you recognise. Done here rather than in the frontend
	because md5 is a line of Python and a dependency in the browser.
	"""
	if not full_name:
		return AVATAR_PALETTE[8]

	digest = hashlib.md5(full_name.encode(), usedforsecurity=False).hexdigest()
	index = int((int(digest[4:6], 16) + 1) / 5.33)
	return AVATAR_PALETTE[index % 8]


def get_user_info() -> dict:
	"""The bits of the session user the sidebar renders."""
	user = frappe.get_cached_doc("User", frappe.session.user)
	return {
		"name": user.name,
		"full_name": user.full_name,
		# The account row reads as name over email, the way the desk's does.
		# Not the same as `name`: for everyone but Administrator the user id is
		# the email, and for Administrator it is the word "Administrator".
		"email": user.email,
		"user_image": user.user_image,
		"avatar_color": get_avatar_color(user.full_name),
		# Whether any of this person's roles opens the desk, which is the same
		# question `User.validate` asks to decide whether they are a System User
		# at all. The search bar reads it: half of what it offers is the desk --
		# doctype lists, new documents, and whatever Global Search finds -- and
		# all of it opens at `/app/...`. Offering somebody a result that will
		# refuse them when they click it is worse than not offering it.
		"desk_access": bool(user.has_desk_access()),
	}
