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

`features` is the site's answer to the few Commons Settings switches the SPA
draws differently for -- today only Bikram Sambat, which decides whether a date
picker offers that calendar. The same switch the desk reads from
`frappe.boot.commons_features`, read here so the two cannot disagree.

Only half of it is this module's. The navigation is; the name is the app's own
setting and is read from `commons.commons_core.settings`, which owns the
document behind it. They are answered together here because the page needs both
before it can paint, which is a fact about the endpoint rather than about either
of them.
"""

import frappe

from commons.better_navigation import pages, workspaces
from commons.commons_core.settings import ENABLE_BIKRAM_SAMBAT, _settings, feature_enabled, title


@frappe.whitelist()
def get_shell() -> dict:
	"""The name and the navigation, together, because they are read together."""
	return {
		"title": title(),
		"workspaces": workspaces.workspaces(),
		"access": pages.access(),
		"features": features(),
		"landing": landing_page(),
	}


def features() -> dict:
	"""What the SPA is told of Bikram Sambat: whether it is on, and the calendar to convert with."""
	if not feature_enabled(ENABLE_BIKRAM_SAMBAT):
		return {"bikram_sambat": False}
	from commons.sambat.table import boot_calendar

	return {"bikram_sambat": True, "bikram_sambat_calendar": boot_calendar()}


def landing_page() -> str | None:
	"""The page key `/commons` opens on, if Commons Settings names one this site has.

	None leaves it to the frontend's own rule, the first row the reader may open
	(`landingRoute` in `frontend/src/data/shell.ts`) -- which is also what
	happens when the named page is one this reader is not offered.
	"""
	key = pages.PAGES.get((_settings() or {}).get("landing_page") or "")
	return key if key and pages.available(key) else None
