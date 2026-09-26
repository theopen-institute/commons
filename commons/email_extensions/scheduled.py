"""A Notification's email held back for a while, and taken back if the document is.

Core sends a Notification's email as soon as the scheduler next empties the
queue, and has no way to stop one once it is queued: the queue has no cancelled
status, and only Administrator may delete from it. For a payment receipt that
is the wrong way round -- the moment after submitting is exactly when a wrong
account or amount is noticed, and by then the payer has the email. So:

* **Delay.** A Notification with "Delay Sending (minutes)" queues its email with
  `send_after` that far ahead, which the scheduler already honours
  (`frappe.email.queue.get_queue`). The Communication on the document's
  timeline is marked Scheduled until it goes out, which is a status core has
  and sets for any email with a `send_after`.
* **Taken back with the document.** Cancelling the document removes whatever
  email its Notifications still have waiting, and says so on its timeline
  (`cancel_pending`, a `doc_events` hook on every doctype). Cancelling is what
  correcting a submitted payment starts with anyway, so the usual way of
  catching a mistake also catches its email.
* **Or by hand.** While an email is waiting, the form says so, with Send Now and
  Don't Send (`scheduled`, `send_now`, `dont_send`). Asked of someone who may
  email the document.

Which emails are a Notification's is recorded on the Communication itself
(`Communication.notification`, a fixture), by `mark_sent` as each is queued.
Nothing else can tell them from an email someone wrote, and only a
Notification's are this module's to take back. The same record is what
"once across amendments" asks of an earlier version (`notification`).
"""

import frappe
from frappe import _
from frappe.utils import add_to_date, now_datetime

NOTIFICATION = "Notification"
MARK_FIELD = "notification"  # on Communication
DELAY_FIELD = "send_delay_minutes"  # on Notification
ONCE_FIELD = "once_across_amendments"  # on Notification

# A queued email the scheduler has not started on. `Partially Sent` is left
# alone: some of its recipients already have it, and taking back the rest would
# leave the timeline saying something that is neither sent nor not.
WAITING = "Not Sent"


def mark_sent(notification, doc, since) -> None:
	"""Record what `notification` has just queued about `doc`, and hold it back if it says to.

	What was just queued is found rather than handed over: core's
	`send_an_email` returns nothing, so its queue rows are the ones about this
	document created since `since`, in this transaction.
	"""
	from frappe.email.doctype.notification.notification import get_reference_doctype, get_reference_name

	queued = frappe.get_all(
		"Email Queue",
		filters={
			"reference_doctype": get_reference_doctype(doc),
			"reference_name": get_reference_name(doc),
			"creation": [">=", since],
		},
		fields=["name", "communication"],
	)
	if not queued:
		return

	delay = int(notification.get(DELAY_FIELD) or 0)
	send_after = add_to_date(now_datetime(), minutes=delay) if delay > 0 else None
	for row in queued:
		if send_after:
			frappe.db.set_value("Email Queue", row.name, "send_after", send_after, update_modified=False)
		if not row.communication:
			continue
		values = {MARK_FIELD: notification.name}
		if send_after:
			values.update({"send_after": send_after, "delivery_status": "Scheduled"})
		frappe.db.set_value("Communication", row.communication, values, update_modified=False)


def waiting(doctype: str, name: str) -> list[dict]:
	"""The emails `doctype`/`name`'s Notifications still have in the queue, soonest first."""
	if not frappe.get_meta("Communication").has_field(MARK_FIELD):
		return []
	communications = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": doctype,
			"reference_name": name,
			"communication_type": "Automated Message",
			MARK_FIELD: ["is", "set"],
		},
		fields=["name", "subject", "recipients", "cc", "send_after", MARK_FIELD],
	)
	if not communications:
		return []
	by_name = {c.name: c for c in communications}
	rows = frappe.get_all(
		"Email Queue",
		filters={"communication": ["in", list(by_name)], "status": WAITING},
		fields=["name", "communication", "send_after"],
		order_by="send_after asc",
	)
	return [
		{
			"queue": row.name,
			"communication": row.communication,
			"subject": by_name[row.communication].subject,
			# Who it goes to, as the timeline should say it: CC when there is no To.
			"recipients": by_name[row.communication].recipients or by_name[row.communication].cc,
			"notification": by_name[row.communication].get(MARK_FIELD),
			"send_after": row.send_after,
		}
		for row in rows
	]


def take_back(doc, row: dict, reason: str) -> None:
	"""Remove one waiting email, and leave a line on the document's timeline in its place.

	The queue row and its recipients are deleted directly: `EmailQueue.on_trash`
	allows only Administrator, which is a rule about clearing out the queue by
	hand, not about a document withdrawing its own unsent email. The
	Communication goes too -- on the timeline it would read as an email the
	payer had, which they never will.
	"""
	frappe.db.delete("Email Queue Recipient", {"parent": row["queue"]})
	frappe.db.delete("Email Queue", {"name": row["queue"]})
	remaining = frappe.db.count("Email Queue", {"communication": row["communication"]})
	if not remaining:
		frappe.delete_doc("Communication", row["communication"], ignore_permissions=True, force=True)
	doc.add_comment(
		"Info",
		_("Email {0} to {1} was not sent: {2}").format(
			frappe.bold(frappe.utils.escape_html(row["subject"] or "")),
			frappe.utils.escape_html(row["recipients"] or ""),
			reason,
		),
	)


def cancel_pending(doc, method=None) -> None:
	"""`on_cancel` on every doctype: a cancelled document's waiting emails are not sent."""
	for row in waiting(doc.doctype, doc.name):
		take_back(doc, row, _("{0} was cancelled").format(_(doc.doctype)))


def _permitted(doctype: str, name: str):
	if not frappe.has_permission(doctype, "email", doc=name):
		frappe.throw(_("Not permitted to email about this {0}.").format(_(doctype)), frappe.PermissionError)
	return frappe.get_doc(doctype, name)


def _row(doctype: str, name: str, queue: str) -> dict:
	for row in waiting(doctype, name):
		if row["queue"] == queue:
			return row
	frappe.throw(_("That email is no longer waiting to be sent."))


@frappe.whitelist()
def scheduled(doctype: str, name: str) -> list[dict]:
	"""What the form's banner shows: the document's emails still waiting."""
	_permitted(doctype, name)
	return waiting(doctype, name)


@frappe.whitelist(methods=["POST"])
def dont_send(doctype: str, name: str, queue: str) -> None:
	doc = _permitted(doctype, name)
	take_back(doc, _row(doctype, name, queue), _("stopped by {0}").format(frappe.session.user))


@frappe.whitelist(methods=["POST"])
def send_now(doctype: str, name: str, queue: str) -> None:
	"""Stop waiting: the scheduler sends it on its next pass, within a minute or so."""
	_permitted(doctype, name)
	row = _row(doctype, name, queue)
	now = now_datetime()
	frappe.db.set_value("Email Queue", queue, "send_after", now, update_modified=False)
	frappe.db.set_value("Communication", row["communication"], "send_after", now, update_modified=False)


DELAYED_CACHE_KEY = "commons_delayed_notification_doctypes"


def delayed_doctypes() -> list[str]:
	"""The doctypes some enabled Notification delays emails for -- where the form looks for waiting ones.

	On every desk boot, and the same for everyone, so cached until a
	Notification changes (`forget_delayed_doctypes`).
	"""
	if not frappe.get_meta(NOTIFICATION).has_field(DELAY_FIELD):
		return []
	return frappe.client_cache.get_value(
		DELAYED_CACHE_KEY,
		generator=lambda: sorted(
			set(
				frappe.get_all(
					NOTIFICATION,
					filters={"enabled": 1, "channel": "Email", DELAY_FIELD: [">", 0]},
					pluck="document_type",
				)
			)
		),
	)


def forget_delayed_doctypes(*args, **kwargs) -> None:
	"""Doc event on Notification: drop `delayed_doctypes`' answer, now and once the save settles."""
	frappe.client_cache.delete_value(DELAYED_CACHE_KEY)
	if db := getattr(frappe.local, "db", None):
		db.after_commit.add(_forget_delayed)
		db.after_rollback.add(_forget_delayed)


def _forget_delayed() -> None:
	frappe.client_cache.delete_value(DELAYED_CACHE_KEY)
