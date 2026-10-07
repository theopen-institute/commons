"""What is read, for whom, and what is kept when a read goes wrong.

Site-less, like `test_purchase_invoice`. What is pinned here is what bills the
site or loses a scan: a capture read without anybody pressing Read, a read
for somebody who could never save it or past the hourly limit, a job that
reads a scan nobody is waiting for any more, and a failure that throws the
scan away instead of keeping it with the reason.
"""

import datetime
import json
import logging
import os
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from commons.document_capture import capture, expense_claim
from commons.document_capture import settings as capture_settings

_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def doctype_defaults() -> frappe._dict:
	"""Document Capture Settings as a never-saved Single loads: the JSON's own defaults."""
	path = os.path.join(
		os.path.dirname(capture.__file__),
		"doctype",
		"document_capture_settings",
		"document_capture_settings.json",
	)
	with open(path) as file:
		fields = json.load(file)["fields"]
	return frappe._dict(
		{
			field["fieldname"]: int(field.get("default") or 0)
			if field["fieldtype"] in ("Check", "Int")
			else field.get("default")
			for field in fields
			if field["fieldtype"] not in ("Section Break", "Column Break")
		}
	)


# Site-less: Document Capture Settings reads as a never-saved Single, which is
# its defaults. `with_settings` changes them for one test.
_no_settings = patch.object(capture_settings, "_settings", return_value=doctype_defaults())


def setUpModule():
	_logger.start()
	_no_settings.start()


def tearDownModule():
	_no_settings.stop()
	_logger.stop()


def with_settings(**changes):
	"""Document Capture Settings as the defaults with `changes`."""
	return patch.object(
		capture_settings, "_settings", return_value=frappe._dict({**doctype_defaults(), **changes})
	)


def _raise(message, exc=ValueError, **kwargs):
	raise exc(message)


class FakeCapture(frappe._dict):
	"""A capture whose `db_set` updates itself, and remembers each call."""

	def __init__(self, **values):
		super().__init__(
			{
				"name": "CAP-1",
				"document_type": "Purchase Invoice",
				"status": "Unread",
				"scan": "/private/files/bill.pdf",
				"owner": "a@example.com",
				"queued_at": None,
				"read_started": None,
				**values,
			}
		)
		self.written = []

	def db_set(self, field, value=None, **kwargs):
		changes = field if isinstance(field, dict) else {field: value}
		self.written.append(changes)
		self.update(changes)

	def check_permission(self, ptype):
		pass

	def reload(self):
		pass


def cache(count=1):
	return SimpleNamespace(
		make_key=lambda key: key,
		incrby=lambda key, by: count,
		expire=lambda key, seconds: None,
		delete_value=lambda key: None,
		get_value=lambda key: None,
		set_value=lambda *args, **kwargs: None,
	)


@patch.object(capture.frappe, "throw", _raise)
class TestAnUploadIsKeptAndNotRead(TestCase):
	"""An upload stores the scan and reads nothing: a reading is billed, and
	only happens when somebody presses Read."""

	def request(self, content=b"%PDF-1.7"):
		upload = SimpleNamespace(stream=SimpleNamespace(read=lambda: content), filename="bill.pdf")
		return SimpleNamespace(files={"file": upload})

	def setUp(self):
		self.enterContext(
			patch.object(capture.frappe, "form_dict", frappe._dict(doctype="Purchase Invoice"), create=True)
		)
		self.enterContext(
			patch.object(capture.frappe, "session", SimpleNamespace(user="a@example.com"), create=True)
		)
		self.get_doc = self.enterContext(patch.object(capture.frappe, "get_doc"))
		self.queued = self.enterContext(patch.object(capture, "_queue"))

	def test_no_permission_no_read(self):
		with (
			patch.object(capture.purchase_invoice, "available", return_value=True),
			patch.object(capture.purchase_invoice, "can_capture", return_value=False),
			patch.object(capture.frappe, "request", self.request(), create=True),
		):
			with self.assertRaises(frappe.PermissionError):
				capture.upload()
		self.get_doc.assert_not_called()
		self.queued.assert_not_called()

	def test_an_empty_file_is_refused_at_once_and_not_counted(self):
		with (
			patch.object(capture, "_require_reading"),
			patch.object(capture.frappe, "request", self.request(b""), create=True),
			patch.object(capture, "_count_read") as counted,
		):
			with self.assertRaisesRegex(ValueError, "empty"):
				capture.upload()
		counted.assert_not_called()
		self.get_doc.assert_not_called()

	def test_a_readable_scan_is_kept_unread_and_not_counted(self):
		stored = FakeCapture()
		stored.insert = lambda: None
		scan = SimpleNamespace(insert=lambda: None, file_url="/private/files/bill.pdf")
		self.get_doc.side_effect = [stored, scan]
		with (
			patch.object(capture, "_require_reading"),
			patch.object(capture.frappe, "request", self.request(), create=True),
			patch.object(capture, "_count_read") as counted,
		):
			self.assertEqual(capture.upload(), {"name": "CAP-1"})
		made, attached = (call.args[0] for call in self.get_doc.call_args_list)
		self.assertEqual(
			(made["document_type"], made["source"], made["status"]), ("Purchase Invoice", "Upload", "Unread")
		)
		self.assertEqual((attached["attached_to_name"], attached["is_private"]), ("CAP-1", 1))
		self.queued.assert_not_called()
		counted.assert_not_called()


@patch.object(capture.frappe, "throw", _raise)
class TestReadingIsAskedFor(TestCase):
	"""`read`, the one way a capture is read: the button, on the page or the
	desk form. The refusals come before anything is queued."""

	def setUp(self):
		self.enterContext(
			patch.object(capture.frappe, "session", SimpleNamespace(user="a@example.com"), create=True)
		)
		self.queued = self.enterContext(patch.object(capture, "_queue"))

	def read(self, stored, count=1, **kwargs):
		with (
			patch.object(capture.frappe, "get_doc", return_value=stored),
			patch.object(capture.frappe, "cache", cache(count), create=True),
			patch.object(capture.purchase_invoice, "available", return_value=True),
			patch.object(capture.purchase_invoice, "can_capture", return_value=True),
		):
			return capture.read("CAP-1", **kwargs)

	def test_an_unread_capture_is_queued(self):
		stored = FakeCapture()
		self.assertEqual(self.read(stored), {"name": "CAP-1"})
		self.queued.assert_called_once_with(stored)

	def test_past_the_hourly_limit_no_read(self):
		with self.assertRaises(frappe.RateLimitExceededError):
			self.read(FakeCapture(), count=capture_settings.hourly_limit() + 1)
		self.queued.assert_not_called()

	def test_the_hourly_limit_is_the_sites(self):
		with with_settings(hourly_limit=5), self.assertRaises(frappe.RateLimitExceededError):
			self.read(FakeCapture(), count=6)
		self.queued.assert_not_called()

	def test_a_limit_of_nought_is_no_limit(self):
		stored = FakeCapture()
		with with_settings(hourly_limit=0):
			self.assertEqual(self.read(stored, count=10_000), {"name": "CAP-1"})
		self.queued.assert_called_once_with(stored)

	def test_one_being_read_is_not_read_twice(self):
		stored = FakeCapture(status="Reading", read_started=frappe.utils.now_datetime())
		with self.assertRaisesRegex(ValueError, "already being read"):
			self.read(stored)
		self.queued.assert_not_called()

	def test_one_without_a_scan_is_refused(self):
		with self.assertRaisesRegex(ValueError, "Attach the scan"):
			self.read(FakeCapture(scan=None))
		self.queued.assert_not_called()

	def test_reading_as_another_kind_drops_the_last_reading(self):
		stored = FakeCapture(status="Read", extracted='{"total": 1}')
		with (
			patch.object(capture.expense_claim, "available", return_value=True),
			patch.object(capture.expense_claim, "can_capture", return_value=True),
		):
			self.read(stored, document_type="Expense Claim")
		self.assertEqual((stored.document_type, stored.extracted), ("Expense Claim", None))
		self.queued.assert_called_once_with(stored)


class TestTheJob(TestCase):
	"""What the background read writes back onto the capture."""

	def run_job(self, stored, queued_at, read=None):
		kind = SimpleNamespace(read_scan=read or (lambda content, progress: {"lines": []}))
		with (
			patch.object(capture.frappe, "get_doc", return_value=stored),
			patch.object(capture.frappe, "cache", cache(), create=True),
			patch.object(capture.frappe, "db", MagicMock(), create=True),
			patch.object(capture.frappe, "log_error") as logged,
			patch.object(capture, "_kind", return_value=kind),
			patch.object(capture, "_scan_content", return_value=b"%PDF"),
			patch.object(capture.claude, "model", return_value="claude-opus-5"),
		):
			capture.run_reading("CAP-1", queued_at)
		return logged

	def queued(self, **values):
		now = frappe.utils.now_datetime()
		return FakeCapture(status="Queued", queued_at=now, **values), str(now)

	def test_a_superseded_job_does_nothing(self):
		stored, _queued_at = self.queued()
		self.run_job(stored, "2020-01-01 00:00:00")
		self.assertEqual(stored.written, [])

	def test_a_job_that_waited_too_long_is_not_read(self):
		long_ago = frappe.utils.now_datetime() - datetime.timedelta(seconds=capture.JOB_TIMEOUT * 3)
		stored = FakeCapture(status="Queued", queued_at=long_ago)
		read = MagicMock()
		self.run_job(stored, str(long_ago), read)
		read.assert_not_called()
		self.assertEqual(stored.status, "Failed")

	def test_a_read_is_stored_as_it_came_back(self):
		stored, queued_at = self.queued()
		self.run_job(stored, queued_at, lambda content, progress: {"total": 100})
		self.assertEqual(stored.status, "Read")
		self.assertEqual(json.loads(stored.extracted), {"total": 100})
		self.assertEqual(stored.model, "claude-opus-5")

	def test_an_api_error_keeps_the_scan_and_says_why(self):
		def refuse(content, progress):
			raise frappe.ValidationError("The service is busy. Try again in a minute.")

		stored, queued_at = self.queued()
		logged = self.run_job(stored, queued_at, refuse)
		self.assertEqual(stored.status, "Failed")
		self.assertEqual(stored.error, "The service is busy. Try again in a minute.")
		self.assertEqual(stored.scan, "/private/files/bill.pdf")
		logged.assert_not_called()

	def test_anything_else_is_logged_and_kept_too(self):
		def crash(content, progress):
			raise KeyError("oops")

		stored, queued_at = self.queued()
		logged = self.run_job(stored, queued_at, crash)
		self.assertEqual(stored.status, "Failed")
		self.assertEqual(stored.error, capture._failed())
		logged.assert_called_once()


class TestWhereACaptureStands(TestCase):
	def test_a_reading_that_ran_too_long_is_failed(self):
		long_ago = frappe.utils.now_datetime() - datetime.timedelta(seconds=capture.JOB_TIMEOUT * 3)
		self.assertEqual(capture._state(FakeCapture(status="Reading", read_started=long_ago)), "failed")

	def test_a_fresh_one_is_still_reading(self):
		now = frappe.utils.now_datetime()
		self.assertEqual(capture._state(FakeCapture(status="Reading", read_started=now)), "reading")

	def test_the_rest_say_their_status(self):
		for status, state in (("Read", "done"), ("Failed", "failed"), ("Unread", "unread")):
			with self.subTest(status=status):
				self.assertEqual(capture._state(FakeCapture(status=status)), state)


class TestEmailedScans(TestCase):
	"""Who is read without being asked, and what counts as a scan."""

	def sort(self, sender, files, user=None, count=1):
		stored = FakeCapture(
			status="Received", scan=None, sender=sender, email_account="Bills", source="Email"
		)
		siblings = []

		def copy_doc(doc):
			sibling = FakeCapture(**doc)
			sibling.name = f"CAP-{len(siblings) + 2}"
			sibling.flags = frappe._dict()
			sibling.insert = lambda **kwargs: None
			siblings.append(sibling)
			return sibling

		communication = frappe._dict(name="COMM-1", subject="Invoice", content="")
		db = SimpleNamespace(get_value=lambda doctype, name, field: "Purchase Invoice", set_value=MagicMock())
		with (
			patch.object(capture.frappe, "get_doc", return_value=stored),
			patch.object(capture.frappe, "get_all", return_value=[communication]),
			patch.object(capture.frappe, "copy_doc", copy_doc),
			patch.object(capture.frappe, "db", db, create=True),
			patch.object(capture.frappe, "cache", cache(count), create=True),
			patch.object(capture, "_email_scans", return_value=files),
			patch.object(capture, "_site_user", return_value=user),
			patch.object(
				capture,
				"_attach",
				side_effect=lambda name, *args, **kwargs: next(f for f in files if f.name == name),
			),
			patch.object(capture.purchase_invoice, "available", return_value=True),
			patch.object(capture, "_queue") as queued,
		):
			capture.sort_email("CAP-1")
		return stored, siblings, queued, db

	def scan(self, name):
		return frappe._dict(name=f"F-{name}", file_name=name, file_url=f"/private/files/{name}", is_private=1)

	def test_a_strangers_scan_waits_unread(self):
		stored, _siblings, queued, db = self.sort("vendor@example.com", [self.scan("bill.pdf")])
		queued.assert_not_called()
		self.assertEqual(
			(stored.status, stored.scan, stored.error), ("Unread", "/private/files/bill.pdf", None)
		)
		db.set_value.assert_not_called()

	def test_a_users_scan_is_theirs_and_waits_unread_too(self):
		stored, _siblings, queued, db = self.sort(
			"peter@example.com", [self.scan("bill.pdf")], user="peter@example.com"
		)
		queued.assert_not_called()
		self.assertEqual(stored.status, "Unread")
		db.set_value.assert_called_once_with(
			"Captured Document", "CAP-1", "owner", "peter@example.com", update_modified=False
		)

	def test_each_scan_gets_a_capture_of_its_own(self):
		stored, siblings, _queued, _db = self.sort(
			"vendor@example.com", [self.scan("a.pdf"), self.scan("b.jpg")]
		)
		self.assertEqual(stored.scan, "/private/files/a.pdf")
		self.assertEqual([sibling.scan for sibling in siblings], ["/private/files/b.jpg"])
		self.assertTrue(siblings[0].flags.sorted_email)

	def test_an_email_with_nothing_to_read_says_so(self):
		stored, _siblings, queued, _db = self.sort("peter@example.com", [], user="peter@example.com")
		queued.assert_not_called()
		self.assertEqual(stored.status, "Unread")
		self.assertIn("no PDF or image", stored.error)

	def test_inline_images_and_other_files_are_not_scans(self):
		files = [
			frappe._dict(file_name="bill.PDF", file_url="/private/files/bill.PDF"),
			frappe._dict(file_name="logo.png", file_url="/private/files/logo.png"),
			frappe._dict(file_name="sheet.xlsx", file_url="/private/files/sheet.xlsx"),
		]
		communication = frappe._dict(name="COMM-1", content='<img src="/private/files/logo.png?fid=1">')
		with patch.object(capture.frappe, "get_all", return_value=files):
			scans = capture._email_scans(communication)
		self.assertEqual([scan.file_name for scan in scans], ["bill.PDF"])


class TestTheDoctypeDoesNotThreadBySubject(TestCase):
	def test_no_subject_field(self):
		"""With one, Frappe would add next month's "Invoice" email to this
		month's capture instead of making a new one."""
		import os

		path = os.path.join(
			os.path.dirname(capture.__file__), "doctype", "captured_document", "captured_document.json"
		)
		with open(path) as file:
			meta = json.load(file)
		self.assertEqual(meta["email_append_to"], 1)
		self.assertFalse(meta.get("subject_field"))
		self.assertEqual(meta["sender_field"], "sender")


@patch.object(capture.frappe, "throw", _raise)
class TestADisabledKind(TestCase):
	"""Switched off in Document Capture Settings: not offered, not uploaded,
	not read, and not taken off an email."""

	def setUp(self):
		for kind in (capture.purchase_invoice, capture.expense_claim):
			self.enterContext(patch.object(kind, "available", return_value=True))
			self.enterContext(patch.object(kind, "can_capture", return_value=True))

	def test_both_are_on_by_default(self):
		self.assertEqual(capture.enabled_kinds(), ["Purchase Invoice", "Expense Claim"])
		self.assertEqual(capture.context()["kinds"], ["Purchase Invoice", "Expense Claim"])

	def test_it_is_not_offered(self):
		with with_settings(enable_expense_claims=0):
			self.assertEqual(capture.context()["kinds"], ["Purchase Invoice"])
			self.assertTrue(capture.can_capture())
		with with_settings(enable_expense_claims=0, enable_purchase_invoices=0):
			self.assertEqual(capture.context()["kinds"], [])
			self.assertFalse(capture.can_capture())
			self.assertFalse(capture.available())

	def test_an_upload_of_it_is_refused(self):
		with (
			with_settings(enable_purchase_invoices=0),
			patch.object(capture.frappe, "form_dict", frappe._dict(doctype="Purchase Invoice"), create=True),
			patch.object(capture.frappe, "get_doc") as made,
		):
			with self.assertRaisesRegex(ValueError, "does not capture scans as Purchase Invoice"):
				capture.upload()
		made.assert_not_called()

	def test_reading_as_it_is_refused(self):
		stored = FakeCapture()
		with (
			with_settings(enable_expense_claims=0),
			patch.object(capture.frappe, "get_doc", return_value=stored),
			patch.object(capture, "_queue") as queued,
		):
			with self.assertRaisesRegex(ValueError, "does not capture"):
				capture.read("CAP-1", document_type="Expense Claim")
		queued.assert_not_called()

	def test_an_email_for_it_is_discarded_with_the_reason(self):
		stored = FakeCapture(status="Received", scan=None, email_account="Receipts", source="Email")
		communication = frappe._dict(name="COMM-1", subject="Lunch", content="")
		db = SimpleNamespace(get_value=lambda doctype, name, field: "Expense Claim")
		with (
			with_settings(enable_expense_claims=0),
			patch.object(capture.frappe, "get_doc", return_value=stored),
			patch.object(capture.frappe, "get_all", return_value=[communication]),
			patch.object(capture.frappe, "db", db, create=True),
			patch.object(capture, "_email_scans") as scans,
			patch.object(capture, "_attach") as attached,
		):
			capture.sort_email("CAP-1")
		self.assertEqual((stored.status, stored.document_type), ("Discarded", "Expense Claim"))
		self.assertIn("does not capture scans as Expense Claim", stored.error)
		scans.assert_not_called()
		attached.assert_not_called()

	def test_an_account_naming_no_kind_falls_back_to_the_first_and_only_that(self):
		db = SimpleNamespace(get_value=lambda doctype, name, field: None)
		with patch.object(capture.frappe, "db", db, create=True):
			self.assertEqual(capture._account_kind("Bills"), capture.DEFAULT_KIND)
			with with_settings(enable_purchase_invoices=0):
				# Not rerouted to receipts, which would change who sees it.
				self.assertEqual(capture._account_kind("Bills"), "Purchase Invoice")

	def test_an_email_account_for_it_is_refused(self):
		account = frappe._dict(append_to="Captured Document", capture_document_type="Expense Claim")
		capture.validate_email_account(account)
		with with_settings(enable_expense_claims=0):
			with self.assertRaisesRegex(ValueError, "does not capture"):
				capture.validate_email_account(account)
			capture.validate_email_account(frappe._dict(account, append_to="Communication"))


class TestTheSettingsDoctype(TestCase):
	def test_each_kind_has_a_switch_on_by_default(self):
		"""What a site that never opened the form captures is every kind."""
		defaults = doctype_defaults()
		for kind in capture.KINDS.values():
			with self.subTest(kind=kind.ENABLE_FIELD):
				self.assertEqual(defaults[kind.ENABLE_FIELD], 1)

	def test_the_hourly_limit_is_sixty_by_default(self):
		"""The limit as it was hard-coded, for a site that never opened the form."""
		self.assertEqual(doctype_defaults().hourly_limit, 60)
		self.assertEqual(capture_settings.hourly_limit(), 60)


@patch.object(capture.frappe, "throw", _raise)
class TestAReceiptIsClaimedByItsOwner(TestCase):
	def test_somebody_elses_receipt_is_refused_before_the_claim(self):
		receipt = FakeCapture(document_type="Expense Claim", status="Read", owner="a@example.com")
		with (
			patch.object(expense_claim, "_require_drafting"),
			patch.object(capture, "for_drafting", return_value=receipt),
			patch.object(expense_claim.frappe, "session", SimpleNamespace(user="b@example.com"), create=True),
			patch("commons.requests.expense.request_expense_claim") as claimed,
		):
			with self.assertRaises(frappe.PermissionError):
				expense_claim.create("CAP-1", {"expenses": []})
		claimed.assert_not_called()

	def test_the_expense_types_are_offered_to_the_model_by_name(self):
		schema = expense_claim.schema(["Travel", "Food"])
		field = schema["properties"]["expenses"]["items"]["properties"]["expense_type"]
		self.assertEqual(field["anyOf"][0]["enum"], ["Travel", "Food"])
		self.assertEqual(
			expense_claim.schema([])["properties"]["expenses"]["items"]["properties"]["expense_type"],
			{"type": "null"},
		)
