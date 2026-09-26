"""What the SPA needs before it can draw anything: its name, and its navigation.

One endpoint, answered once per page load. A production build never calls it --
`commons/www/commons.py` puts the same answer on `window` through the page's
boot data, so the sidebar has a name and its rows on first paint rather than
after a round trip. The Vite dev server serves `index.html` without the Jinja
pass, so there the frontend asks. That is the split `website_link.py` already
makes for the Website button, and this follows it.

Whitelisted, and the same answer either way. Almost nothing here is about the
caller: the title is the site's name for itself, and the workspaces are what the
site offers, not what this user may open -- see `workspaces.py` on why
permission is the frontend's half of the answer.

The exception is `access`: for the few pages whose row waits on a permission
that no request section answers (the register, reconciliation, capture), this
user's answer, from `pages.access`. Asked here because the browser asking it
meant loading each of those pages' code on every boot to hold the question.

Only half of it is this module's. The navigation is; the name is the app's own
setting and is read from `commons.commons_core.settings`, which owns the
document behind it. They are answered together here because the page needs both
before it can paint, which is a fact about the endpoint rather than about either
of them.
"""

import frappe

from commons.better_navigation import pages, workspaces
from commons.commons_core.settings import title


@frappe.whitelist()
def get_shell() -> dict:
	"""The name and the navigation, together, because they are read together."""
	return {"title": title(), "workspaces": workspaces.workspaces(), "access": pages.access()}
