"""Captured Document: every scan's way in, whether it was uploaded or emailed.

A scan becomes a `Captured Document` before anything reads it. The record
holds the scan through everything that can go wrong on the way to a draft: an
API error, a key removed, a worker that died, a reader who closed the dialog.
The scan is then still there to read again, and nobody has to find the paper
or the email a second time. What becomes of the record is described in
`doctype.captured_document`, and each kind of draft (`purchase_invoice`,
`expense_claim`) keeps its own schema, matching and `create`.

Two ways in
-----------
`upload`
	The page's own. The file arrives as multipart, the way Frappe's
	`upload_file` takes one, with `doctype` saying what it should become. It is
	saved as a private File on a new capture, which waits unread.
Email
	An Email Account whose "Append To" is Captured Document. Frappe's inbound
	mail creates the capture itself (`InboundMail._create_reference_document`),
	fills in the sender and the account, and saves the email's attachments to
	the Communication, not to the capture. So the capture's `after_insert`
	queues `sort_email` to run once that email has been committed. It takes
	each PDF or image off the email and gives it a capture of its own. The kind
	comes from the account's `capture_document_type`. Inline images are skipped,
	since they are logos and signatures.

	The doctype has no `subject_field`, deliberately. With one, Frappe would
	thread a new email onto an open capture whose title matched, and a
	supplier's monthly "Invoice" would add to last month's capture rather
	than starting its own.

Nothing is read until somebody asks
-----------------------------------
A read is billed, so no capture is read when it arrives, however it arrived.
It waits `Unread` until a person presses Read, on the page or on the desk
form, which is `read`, within that person's hourly limit.

An emailed scan whose sender is an enabled user here is theirs (`owner`), so
the page lists it for them and an expense receipt can be claimed by them.
The sender is whatever the From header says. Anything that checks it (SPF,
DKIM) is the mail server's job, not this one's.

The job
-------
`run_reading` reads the scan in the `long` queue and writes the outcome onto
the record: `Read` with `extracted`, or `Failed` with `error`. Progress (which
step, how many lines copied so far) is kept in the cache, because it is only
useful while somebody is watching. A job RQ killed, or whose worker died,
writes nothing, so a capture `Queued` or `Reading` for longer than the job is
allowed to take is reported as failed (`_overdue`), and can be read again.
Each job is tied to the `queued_at` it was queued with, so if a capture is
queued again, the older job finds it has been superseded and does nothing.

Who sees which
--------------
Each kind's rule is Document Capture Settings' (`settings.visibility`): either
anybody who may create the kind's document sees every capture of it, as
everyone on a shared accounts inbox would, or only its sender does. By
default a purchase invoice capture is the accounts team's and an expense
receipt its sender's alone, as they were before the rule was the site's.
`has_permission` and `permission_query_conditions` narrow the role permissions
to that. They can only deny, and the settings' supervisor role (System Manager
by default) and Administrator are left alone.

Which kinds
-----------
`KINDS` is the one list of them; everything else, the page included (through
`context`), is derived from it. A kind the site has switched off in Document
Capture Settings is not offered, its uploads and reads are refused, and an
email to an account that captures it is discarded with the reason
(`sort_email`). Captures already made of it stay visible by the rule above.
"""

import json

import frappe
from frappe import _
from frappe.utils import now_datetime, time_diff_in_seconds

from commons.api_integrations.claude import client as claude
from commons.api_integrations.claude import documents
from commons.commons_core import apps
from commons.document_capture import expense_claim, purchase_invoice
from commons.document_capture import settings as capture_settings

CAPTURED_DOCUMENT = "Captured Document"

# What each kind of capture becomes, and the module that reads it: the one list
# of kinds. Each has `available`, `can_capture`, `read_scan` and `reading`, and
# its switches in Document Capture Settings, `ENABLE_FIELD` and
# `VISIBILITY_FIELD`; see `purchase_invoice`. The first is what an email
# becomes when its account does not say (`_account_kind`).
KINDS = {
	purchase_invoice.PURCHASE_INVOICE: purchase_invoice,
	expense_claim.EXPENSE_CLAIM: expense_claim,
}
DEFAULT_KIND = next(iter(KINDS))

# Reads per person per hour. A person working through a pile of scans needs
# one a minute at most, and a read costs a few cents.
HOURLY_LIMIT = 60

# Seconds. How long Claude may take over one scan, and a margin over it for the
# job as a whole. A scan is usually read in under a minute; a photographed
# ten-page invoice can take several.
READ_TIMEOUT = 300
JOB_TIMEOUT = READ_TIMEOUT + 120

# Seconds past `JOB_TIMEOUT` before a capture still queued or reading is taken
# to be lost: long enough for RQ to notice, short enough that nobody waits long.
MARGIN = 60

# How long the progress of a reading is kept for the page to ask after.
PROGRESS_TTL = 3600

# What an email may carry that is worth reading. Anything else (a spreadsheet,
# a Word file, a calendar invite) is left on the Communication.
SCAN_EXTENSIONS = frozenset({"pdf", "jpg", "jpeg", "png", "webp", "gif"})

# Statuses a capture leaves the page's list in.
FINISHED = ("Drafted", "Discarded")


# --------------------------------------------------------------------------- #
# What this site and this person can capture                                  #
# --------------------------------------------------------------------------- #


def _kind(document_type: str | None):
	kind = KINDS.get(document_type or "")
	if not kind:
		frappe.throw(_("Scans cannot be drafted as {0}.").format(document_type or _("nothing")))
	return kind


def enabled_kinds() -> list[str]:
	"""The kinds this site captures, by Document Capture Settings."""
	return [name for name, kind in KINDS.items() if capture_settings.enabled(kind)]


def _offered(kind) -> bool:
	"""Whether this site can read `kind` and captures it: set up, and switched
	on. The app and the key are asked first, so a site without them never
	reads the settings."""
	return kind.available() and capture_settings.enabled(kind)


def available() -> bool:
	"""Whether this site can read scans into any kind of draft."""
	return any(_offered(kind) for kind in KINDS.values())


def can_capture() -> bool:
	"""Whether this person can use the page: some kind is available here and
	theirs to draft. Stops at the first, because the shell asks on every load
	and a receipt's test looks the reader's employee record up."""
	return any(_offered(kind) and kind.can_capture() for kind in KINDS.values())


def kinds() -> list[str]:
	"""The kinds of draft this person may capture, on this site. What the page
	offers, through `context`."""
	return [name for name, kind in KINDS.items() if _offered(kind) and kind.can_capture()]


def _require_enabled(kind) -> None:
	if not capture_settings.enabled(kind):
		frappe.throw(_("This site does not capture scans as {0}.").format(_(kind_label(kind))))


def _require_reading(kind) -> None:
	"""For a read, which is billed: the kind is captured here, set up, and
	theirs to make."""
	_require_enabled(kind)
	if not kind.available():
		frappe.throw(_("Reading scans into a {0} is not set up on this site.").format(_(kind_label(kind))))
	if not kind.can_capture():
		frappe.throw(
			_("You are not allowed to make a {0}.").format(_(kind_label(kind))), frappe.PermissionError
		)


def kind_label(kind) -> str:
	return next(name for name, module in KINDS.items() if module is kind)


@frappe.whitelist()
def context() -> dict:
	"""What the page offers this person: which kinds of scan it takes from them."""
	return {"kinds": kinds(), "hourly_limit": HOURLY_LIMIT}


# --------------------------------------------------------------------------- #
# Taking a scan in                                                            #
# --------------------------------------------------------------------------- #


@frappe.whitelist(methods=["POST"])
def upload() -> dict:
	"""Keep the scan in the request's `file` field as a new capture.

	`doctype` is what it should become. Answers with the new capture's name.
	Nothing is read: that is `read`, when the person asks for it.
	"""
	kind = _kind(frappe.form_dict.get("doctype"))
	_require_reading(kind)
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose a scan to read."))
	content = upload.stream.read()
	documents.check(content)

	file_name = upload.filename or "scan"
	capture = frappe.get_doc(
		{
			"doctype": CAPTURED_DOCUMENT,
			"document_type": kind_label(kind),
			"source": "Upload",
			"status": "Unread",
			"subject": file_name[:140],
		}
	)
	capture.insert()
	scan = frappe.get_doc(
		{
			"doctype": "File",
			"file_name": file_name,
			"attached_to_doctype": CAPTURED_DOCUMENT,
			"attached_to_name": capture.name,
			"attached_to_field": "scan",
			"is_private": 1,
			"content": content,
		}
	)
	scan.insert()
	capture.db_set("scan", scan.file_url)
	return {"name": capture.name}


def queue_email_sorting(name: str) -> None:
	"""From the capture's `after_insert`, for one Frappe's inbound mail made.
	After the commit, because the email's attachments are saved after the
	capture is inserted, in the same transaction."""
	frappe.enqueue(
		"commons.document_capture.capture.sort_email",
		queue="short",
		enqueue_after_commit=True,
		name=name,
	)


def sort_email(name: str) -> None:
	"""Give each PDF or image on the email a capture, owned by the sender
	where the sender is a user here. None of them is read.

	The first scan goes on the capture Frappe made; any others get captures of
	their own, alike in everything but the scan.
	"""
	capture = frappe.get_doc(CAPTURED_DOCUMENT, name)
	if capture.status != "Received":
		return
	communication = frappe.get_all(
		"Communication",
		filters={
			"reference_doctype": CAPTURED_DOCUMENT,
			"reference_name": name,
			"sent_or_received": "Received",
		},
		fields=["name", "subject", "content"],
		order_by="creation asc",
		limit=1,
	)
	document_type = _account_kind(capture.email_account)
	values = {"document_type": document_type, "status": "Unread"}
	if not capture_settings.enabled(_kind(document_type)):
		# Refused: the scans stay on the email, and nothing is copied for a
		# kind nobody here will draft.
		capture.db_set(
			{
				"document_type": document_type,
				"status": "Discarded",
				"communication": communication[0].name if communication else None,
				"error": _("This site does not capture scans as {0}.").format(_(document_type)),
			}
		)
		return
	if not communication:
		capture.db_set({**values, "error": _("The email this came from was not found.")})
		return
	communication = communication[0]
	values["communication"] = communication.name
	values["subject"] = (communication.subject or "")[:140] or None

	scans = _email_scans(communication)
	if not scans:
		capture.db_set({**values, "error": _("The email had no PDF or image attached.")})
		return

	user = _site_user(capture.sender)
	captures = [capture]
	for _extra in scans[1:]:
		sibling = frappe.copy_doc(capture)
		sibling.update({**values, "source": "Email", "scan": None})
		# Sorted already, here: not a capture for `before_insert` to mark
		# received and send back through this function.
		sibling.flags.sorted_email = True
		sibling.insert(ignore_permissions=True)
		captures.append(sibling)

	for each, scan in zip(captures, scans, strict=True):
		copied = _attach(scan.name, CAPTURED_DOCUMENT, each.name, field="scan")
		each.db_set({**values, "scan": copied.file_url, "error": None})
		if user:
			# The sender's, so the page lists it for them and an expense
			# receipt can be claimed by them alone.
			frappe.db.set_value(CAPTURED_DOCUMENT, each.name, "owner", user, update_modified=False)


def _account_kind(email_account: str | None) -> str:
	"""What the account's captures become, from its `capture_document_type`,
	and `DEFAULT_KIND` where it names none of `KINDS`. Not another enabled kind
	in its place: receipts read as invoices would be the accounts team's to see.
	"""
	kind = email_account and frappe.db.get_value("Email Account", email_account, "capture_document_type")
	return kind if kind in KINDS else DEFAULT_KIND


def validate_email_account(doc, method=None) -> None:
	"""An Email Account's `capture_document_type` is a kind this site captures.

	The field's options are every kind; this narrows them to the enabled ones,
	for an account that appends to Captured Document. For a `doc_events`
	`validate` hook on Email Account.
	"""
	kind = doc.get("capture_document_type")
	if not kind or doc.get("append_to") != CAPTURED_DOCUMENT:
		return
	if kind not in enabled_kinds():
		frappe.throw(_("This site does not capture scans as {0}.").format(_(kind)))


def _email_scans(communication) -> list:
	"""The files on an email worth reading, in the order they were attached.

	An image the email's body shows inline is a logo or a signature, and is
	left out. `InboundMail.replace_inline_images` has put the file's URL in the
	body where the `cid:` reference was, and that URL is how one is recognised.
	"""
	content = communication.content or ""
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Communication", "attached_to_name": communication.name},
		fields=["name", "file_name", "file_url", "is_private"],
		order_by="creation asc",
	)
	return [
		file
		for file in files
		if (file.file_name or "").rsplit(".", 1)[-1].lower() in SCAN_EXTENSIONS
		and file.file_url not in content
	]


def _site_user(email: str | None) -> str | None:
	"""The enabled user an address belongs to, if any. Administrator and Guest
	never count: nobody sends mail as them."""
	if not email:
		return None
	user = frappe.db.get_value("User", {"email": email, "enabled": 1}, "name") or frappe.db.get_value(
		"User", {"name": email, "enabled": 1}, "name"
	)
	return None if user in (None, "Administrator", "Guest") else user


# --------------------------------------------------------------------------- #
# Reading                                                                     #
# --------------------------------------------------------------------------- #


@frappe.whitelist(methods=["POST"])
def read(name: str, document_type: str | None = None) -> dict:
	"""Send a held or failed capture to be read, or read again.

	`document_type` reads it as another kind than it was. A reading is only of
	one kind, so changing it clears the last one.
	"""
	capture = frappe.get_doc(CAPTURED_DOCUMENT, name)
	capture.check_permission("write")
	document_type = document_type or capture.document_type
	kind = _kind(document_type)
	_require_reading(kind)
	state = _state(capture)
	if state in ("queued", "reading"):
		frappe.throw(_("{0} is already being read.").format(name))
	if capture.status in FINISHED:
		frappe.throw(_("{0} is {1}, so there is nothing to read.").format(name, _(capture.status).lower()))
	if not capture.scan:
		frappe.throw(_("Attach the scan to {0} before reading it.").format(name))
	_count_read(frappe.session.user)
	if document_type != capture.document_type:
		capture.db_set({"document_type": document_type, "extracted": None, "model": None, "read_at": None})
	_queue(capture)
	return {"name": capture.name}


def _queue(capture) -> None:
	queued_at = now_datetime()
	capture.db_set({"status": "Queued", "queued_at": queued_at, "read_started": None, "error": None})
	frappe.cache.delete_value(_progress_key(capture.name))
	frappe.enqueue(
		"commons.document_capture.capture.run_reading",
		queue="long",
		timeout=JOB_TIMEOUT,
		enqueue_after_commit=True,
		name=capture.name,
		queued_at=str(queued_at),
	)


def run_reading(name: str, queued_at: str) -> None:
	"""The background job. Reads the scan and writes the outcome onto the
	capture; see the module docstring."""
	capture = frappe.get_doc(CAPTURED_DOCUMENT, name)
	if capture.status != "Queued" or str(capture.queued_at) != queued_at:
		# Queued again since, or read, drafted or discarded: another job's.
		return
	if _overdue(capture):
		# The page has been told this reading failed. Reading it now would
		# bill the site for an answer nobody collects.
		capture.db_set({"status": "Failed", "error": _lost()})
		return
	capture.db_set({"status": "Reading", "read_started": now_datetime()})
	frappe.db.commit()

	kind = _kind(capture.document_type)
	key = _progress_key(name)

	def progress(**changes):
		state = frappe.cache.get_value(key) or {}
		frappe.cache.set_value(key, {**state, **changes}, expires_in_sec=PROGRESS_TTL)

	try:
		extracted = kind.read_scan(_scan_content(capture), progress)
	except frappe.ValidationError as error:
		frappe.db.rollback()
		capture.db_set({"status": "Failed", "error": str(error) or _failed()})
		return
	except Exception:
		frappe.db.rollback()
		# Logged without the document: the traceback, not the scan.
		frappe.log_error(title="Document capture failed")
		capture.db_set({"status": "Failed", "error": _failed()})
		return
	finally:
		frappe.cache.delete_value(key)
	capture.db_set(
		{
			"status": "Read",
			"extracted": json.dumps(extracted),
			"model": claude.model(),
			"read_at": now_datetime(),
			"error": None,
		}
	)


def _scan_file(capture) -> str | None:
	"""The File record of the capture's scan, if it is still attached."""
	if not capture.scan:
		return None
	files = frappe.get_all(
		"File",
		filters={
			"file_url": capture.scan,
			"attached_to_doctype": CAPTURED_DOCUMENT,
			"attached_to_name": capture.name,
		},
		pluck="name",
		limit=1,
	)
	return files[0] if files else None


def _scan_content(capture) -> bytes:
	scan = _scan_file(capture)
	if not scan:
		frappe.throw(_("The scan is no longer attached. Attach it again."))
	return frappe.get_doc("File", scan).get_content()


def _progress_key(name: str) -> str:
	return f"commons:captured_document:progress:{name}"


def _overdue(capture) -> bool:
	"""Whether a capture queued or reading never will finish: longer than the
	job is allowed, in the queue or running."""
	if capture.status not in ("Queued", "Reading"):
		return False
	since = capture.read_started or capture.queued_at
	if not since:
		return False
	return time_diff_in_seconds(now_datetime(), since) > JOB_TIMEOUT + MARGIN


def _state(capture) -> str:
	"""Where a capture stands, for the page: `queued`, `reading`, `done`,
	`failed`, or its status in lower case when nothing is happening to it."""
	if _overdue(capture):
		return "failed"
	return {"Queued": "queued", "Reading": "reading", "Read": "done", "Failed": "failed"}.get(
		capture.status, capture.status.lower()
	)


def _lost() -> str:
	return _(
		"The reading stopped without an answer. It may have run out of time, or the worker stopped. Read it again."
	)


def _failed() -> str:
	return _("Something went wrong reading the scan.")


def _count_read(user: str) -> None:
	"""Count a read against this person's hourly limit, in a rolling hour that
	starts at their first, and refuse one past it."""
	key = frappe.cache.make_key(f"commons:document_capture:reads:{user}")
	count = frappe.cache.incrby(key, 1)
	if count == 1:
		frappe.cache.expire(key, 3600)
	if count > HOURLY_LIMIT:
		frappe.throw(
			_("That is {0} scans in the last hour, which is the limit. Try again later.").format(
				HOURLY_LIMIT
			),
			frappe.RateLimitExceededError,
		)


# --------------------------------------------------------------------------- #
# The page's view of a capture                                                #
# --------------------------------------------------------------------------- #

LIST_FIELDS = [
	"name",
	"document_type",
	"status",
	"source",
	"subject",
	"sender",
	"sender_name",
	"scan",
	"error",
	"owner",
	"creation",
	"queued_at",
	"read_started",
]


@frappe.whitelist()
def waiting() -> list[dict]:
	"""The captures this person may draft that have not become a draft yet,
	newest first."""
	allowed = kinds()
	if not allowed:
		return []
	rows = frappe.get_list(
		CAPTURED_DOCUMENT,
		fields=LIST_FIELDS,
		filters={"status": ["not in", FINISHED], "document_type": ["in", allowed]},
		order_by="creation desc",
		limit=100,
	)
	for row in rows:
		row.state = _state(row)
		if row.state == "failed" and row.status in ("Queued", "Reading"):
			row.error = _lost()
	return rows


@frappe.whitelist()
def status(name: str) -> dict:
	"""Where a capture's reading has got to, in the shape the page polls for:
	`queued` or `reading` (with the `step` and the `lines` copied so far),
	`done` with the `result` the dialog opens with, or `failed` with the
	`error`."""
	capture = frappe.get_doc(CAPTURED_DOCUMENT, name)
	capture.check_permission("read")
	state = _state(capture)
	if state in ("queued", "reading"):
		progress = frappe.cache.get_value(_progress_key(name)) or {}
		return {"status": state, "step": progress.get("step"), "lines": progress.get("lines") or 0}
	if state == "done":
		return {"status": "done", "result": opened(capture)}
	if state == "failed":
		return {"status": "failed", "error": _lost() if _overdue(capture) else capture.error or _failed()}
	return {
		"status": "failed",
		"error": {
			"unread": _("{0} has not been sent to be read."),
			"received": _("{0} is still being taken off its email."),
			"drafted": _("{0} is already a draft."),
			"discarded": _("{0} was discarded."),
		}.get(state, _("{0} cannot be read.")).format(name),
	}


@frappe.whitelist()
def open_capture(name: str) -> dict:
	"""What the dialog opens with for a capture that has been read."""
	capture = frappe.get_doc(CAPTURED_DOCUMENT, name)
	capture.check_permission("read")
	if capture.status != "Read":
		frappe.throw(_("{0} has not been read.").format(name))
	return opened(capture)


def opened(capture) -> dict:
	"""The reading, put next to this site's records as the viewer may see them,
	and what the dialog shows of the capture itself."""
	extracted = json.loads(capture.extracted) if isinstance(capture.extracted, str) else capture.extracted
	return {
		**_kind(capture.document_type).reading(capture, extracted),
		"model": capture.model,
		"capture": {
			"name": capture.name,
			"document_type": capture.document_type,
			"scan": capture.scan,
			"file_name": (capture.scan or "").rsplit("/", 1)[-1],
			"subject": capture.subject,
			"sender": capture.sender,
			"owner": capture.owner,
		},
	}


@frappe.whitelist(methods=["POST"])
def discard(name: str) -> None:
	"""Put a capture aside without drafting it. Kept, not deleted: an email
	it came from still points at it."""
	capture = frappe.get_doc(CAPTURED_DOCUMENT, name)
	capture.check_permission("write")
	if _state(capture) in ("queued", "reading"):
		frappe.throw(_("{0} is being read. Discard it once the reading is done.").format(name))
	if capture.status == "Drafted":
		frappe.throw(_("{0} is already a draft.").format(name))
	capture.db_set("status", "Discarded")


# --------------------------------------------------------------------------- #
# From a capture to a draft                                                   #
# --------------------------------------------------------------------------- #


def for_drafting(name: str, doctype: str):
	"""The capture a draft is about to be made from, once it is sure it may be.
	Called before the insert, so a refusal leaves nothing behind."""
	capture = frappe.get_doc(CAPTURED_DOCUMENT, name)
	capture.check_permission("write")
	if capture.document_type != doctype:
		frappe.throw(_("{0} was read as a {1}.").format(name, _(capture.document_type)))
	if capture.status == "Drafted":
		frappe.throw(_("{0} is already {1} {2}.").format(name, _(capture.draft_doctype), capture.draft_name))
	if capture.status != "Read":
		frappe.throw(_("{0} has not been read.").format(name))
	return capture


def link_draft(capture, draft) -> None:
	"""Mark the capture drafted, and attach its scan to the draft.

	A second File on the same `file_url`, as an attachment copied in the desk
	would be: the scan is stored once, and a private file may be read by
	anybody who may read either document it is attached to.
	"""
	scan = _scan_file(capture)
	if scan:
		_attach(scan, draft.doctype, draft.name)
	capture.db_set({"status": "Drafted", "draft_doctype": draft.doctype, "draft_name": draft.name})


def _attach(file_name: str, doctype: str, name: str, field: str | None = None):
	"""The File named `file_name`, attached to this document as well.

	Frappe's own copy, which reuses the stored file rather than writing it
	again. Without permission checks, because every caller has checked
	already: the email sorting runs as the system, and `link_draft` follows an
	insert the reader was allowed.
	"""
	return frappe.get_doc("File", file_name).create_attachment_copy(
		doctype, name, field, ignore_permissions=True
	)


# --------------------------------------------------------------------------- #
# Permissions                                                                 #
# --------------------------------------------------------------------------- #


def _unrestricted(user: str) -> bool:
	"""Administrator, or a holder of the settings' supervisor role."""
	if user == "Administrator":
		return True
	role = capture_settings.supervisor_role()
	return bool(role) and role in frappe.get_roles(user)


def _sees_all_of(name: str, user: str) -> bool:
	"""Whether `user` sees every capture of the kind `name`, not only their own:
	the kind is shared with whoever may create its document, and they may."""
	kind = KINDS.get(name)
	if not kind or capture_settings.visibility(kind) != capture_settings.ANYONE:
		return False
	return apps.has_doctype(name) and bool(frappe.has_permission(name, "create", user=user))


def _shared_kinds(user: str) -> list[str]:
	"""The kinds whose every capture `user` sees."""
	return [name for name in KINDS if _sees_all_of(name, user)]


def has_permission(doc, ptype=None, user=None):
	"""Deny what the role permissions grant beyond the rule in the module
	docstring: a capture to its owner, and to whoever may create its kind's
	document where the kind is shared that way.

	True where it has no objection, never None: Frappe 16 reads None from a
	controller hook as a refusal. True grants nothing the roles do not."""
	user = user or frappe.session.user
	if _unrestricted(user) or doc.owner == user:
		return True
	return _sees_all_of(doc.document_type, user)


def permission_query_conditions(user=None) -> str:
	user = user or frappe.session.user
	if _unrestricted(user):
		return ""
	own = f"`tab{CAPTURED_DOCUMENT}`.`owner` = {frappe.db.escape(user)}"
	shared = _shared_kinds(user)
	if shared:
		names = ", ".join(frappe.db.escape(name) for name in shared)
		return f"({own} or `tab{CAPTURED_DOCUMENT}`.`document_type` in ({names}))"
	return f"({own})"
