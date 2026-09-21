# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The desk's notification list, shaped for a sidebar that has no boot.

The desk widget reads two different things: `get_notification_logs` for the
rows and `frappe.boot.notification_unread_count` for the badge. This app has no
boot, and the badge decides whether its sidebar row is drawn at all, so both
have to come back from one call.

It is not a thin wrapper over `get_notification_logs`, for two reasons:

* That endpoint's permission query exempts Administrator (see
  `frappe.desk.doctype.notification_log.notification_log.get_permission_query_conditions`),
  so an administrator asking for "my notifications" is handed the whole site's.
  A personal list must be the session user's own, so the filter is explicit.
* It returns `fields=["*"]`, which includes `email_content` -- a rendered email
  per row, for a panel that shows one line of text.

Marking them read is core's own (`mark_as_read` / `mark_all_as_read`): those are
already scoped to the session user, and there is nothing to improve on.
"""

import html

import frappe
from frappe.utils import cint, pretty_date, strip_html

DOCTYPE = "Notification Log"

# Everything the panel draws, and nothing else.
FEED_FIELDS = (
	"name",
	"title",
	"subject",
	"type",
	"document_type",
	"document_name",
	"source_doctype",
	"source_name",
	"link",
	"from_user",
	"read",
	"creation",
)


def _as_text(value: str | None) -> str:
	"""One line of plain text from a field that may carry markup.

	`title` is written with markup in it -- core wraps the subject in
	`<b class="subject-title">` -- and the desk renders that as HTML. Here it is
	flattened on the way out instead: the panel interpolates it as text, so
	stripping server-side keeps every caller from having to remember to.

	Unescaped after stripping, or a subject written with entities in it arrives
	as "Leave&nbsp;Application". `split()` then collapses the U+00A0 that a
	`&nbsp;` unescapes to, along with the rest of the whitespace.
	"""
	text = html.unescape(strip_html(value or "")).replace("\xa0", " ")
	return " ".join(text.split())


@frappe.whitelist()
def get_notification_feed(limit: int = 20) -> dict:
	"""Return the session user's recent notifications and their unread count.

	`unread` counts every unread notification, not just the ones in `logs` --
	it is the badge, and a badge that stopped at the page size would be wrong
	exactly when it matters most.
	"""
	limit = max(1, min(cint(limit) or 20, 100))
	mine = {"for_user": frappe.session.user}

	logs = frappe.get_list(
		DOCTYPE,
		filters=mine,
		fields=FEED_FIELDS,
		order_by="creation desc",
		limit_page_length=limit,
	)

	for log in logs:
		# `title` is the canonical field; `subject` is the legacy one, which is
		# still all some rows have. Same fallback the desk widget makes.
		log.text = _as_text(log.title) or _as_text(log.subject)
		log.read = bool(log.read)
		# "2 hours ago", worked out here rather than in the browser: `creation`
		# is a naive datetime in the site's timezone, and the browser has no way
		# to know what that is.
		log.when = pretty_date(log.creation)
		del log.title
		del log.subject

	return {
		"notifications": logs,
		"unread": frappe.db.count(DOCTYPE, {**mine, "read": 0}),
	}
