"""The background reading's plumbing: who may ask, and when to stop waiting.

Site-less. The cache is a dict and the queue a mock, so what is under test is
the part that decides what the browser is told: a job RQ killed is reported as
failed within minutes rather than left "reading" for an hour, and a reading is
nobody's but its starter's.
"""

import logging
import time
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from commons.api_integrations.claude import jobs

_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


STARTER = "accounts@example.org"


class JobTestCase(TestCase):
	def setUp(self):
		self.store = {}
		cache = SimpleNamespace(
			get_value=lambda key, expires=False: self.store.get(key),
			set_value=lambda key, value, expires_in_sec=None: self.store.__setitem__(key, value),
			delete_value=lambda key: self.store.pop(key, None),
			# Where `_()` looks for translations: none, rather than a logged error.
			hget=lambda *args, **kwargs: {},
		)
		self.enterContext(patch.object(jobs.frappe, "cache", cache, create=True))
		self.enterContext(patch.object(jobs.frappe, "session", SimpleNamespace(user=STARTER), create=True))
		self.enterContext(patch.object(jobs.frappe, "log_error"))
		self.enqueue = self.enterContext(patch.object(jobs.frappe, "enqueue"))
		self.job = jobs.Job("test_reading", "commons.example.run", timeout=300)

	def state(self, token="T"):
		return self.store[self.job.state_key(token)]

	def put(self, token="T", **state):
		self.store[self.job.state_key(token)] = {"status": "queued", "user": STARTER, **state}
		self.store[self.job.file_key(token)] = b"%PDF-1.7"

	def run_job(self, read, token="T"):
		self.job.run(token, read, missing="missing", failed="failed", lost="lost", log_title="t")


class TestStarting(JobTestCase):
	def test_the_file_is_cached_and_the_job_queued_with_its_timeout(self):
		with patch.object(jobs.frappe, "generate_hash", return_value="T"):
			token = self.job.start(b"scan", lines=0)
		self.assertEqual(token, "T")
		self.assertEqual(self.store[self.job.file_key("T")], b"scan")
		self.assertEqual(self.state()["status"], "queued")
		self.assertEqual(self.state()["user"], STARTER)
		self.assertEqual(self.state()["lines"], 0)
		self.assertAlmostEqual(self.state()["queued_at"], time.time(), delta=5)
		self.enqueue.assert_called_once_with("commons.example.run", queue="long", timeout=300, token="T")


class TestAskingAfterIt(JobTestCase):
	def test_only_the_starter_may_ask_and_the_plumbing_is_not_shown(self):
		self.put(queued_at=time.time())
		self.assertEqual(self.job.status("T", lost="lost"), {"status": "queued"})
		with (
			patch.object(jobs.frappe, "session", SimpleNamespace(user="someone@example.org")),
			patch.object(jobs.frappe, "throw", side_effect=frappe.DoesNotExistError) as thrown,
		):
			with self.assertRaises(frappe.DoesNotExistError):
				self.job.status("T", lost="lost")
		self.assertIs(thrown.call_args.args[1], frappe.DoesNotExistError)

	def test_a_job_running_past_its_timeout_is_reported_failed(self):
		self.put(status="reading", queued_at=time.time() - 1000, started_at=time.time() - self.job.limit - 1)
		self.assertEqual(self.job.status("T", lost="It stopped."), {"status": "failed", "error": "It stopped."})

	def test_a_long_wait_in_the_queue_before_a_long_run_is_not_counted_against_it(self):
		self.put(status="reading", queued_at=time.time() - 10_000, started_at=time.time() - 10)
		self.assertEqual(self.job.status("T", lost="lost")["status"], "reading")

	def test_a_job_nothing_picked_up_is_reported_failed_too(self):
		self.put(queued_at=time.time() - self.job.limit - 1)
		self.assertEqual(self.job.status("T", lost="lost")["status"], "failed")

	def test_a_finished_reading_is_never_overdue(self):
		for status in ("done", "failed"):
			with self.subTest(status=status):
				self.assertFalse(self.job.overdue({"status": status, "started_at": 1}))

	def test_a_state_without_times_is_left_to_expire(self):
		self.assertFalse(self.job.overdue({"status": "reading"}))


class TestTheJob(JobTestCase):
	def test_a_reading_starts_with_its_time_and_ends_with_its_result(self):
		self.put(queued_at=time.time())

		def read(content, progress):
			self.assertEqual(content, b"%PDF-1.7")
			self.assertEqual(self.state()["status"], "reading")
			self.assertIsNotNone(self.state()["started_at"])
			progress(lines=3, user="someone@example.org")
			self.assertEqual(self.state()["lines"], 3)
			return {"total": 1}

		self.run_job(read)
		self.assertEqual(self.state()["status"], "done")
		self.assertEqual(self.state()["result"], {"total": 1})
		# Progress cannot hand the reading to somebody else.
		self.assertEqual(self.state()["user"], STARTER)
		self.assertNotIn(self.job.file_key("T"), self.store)

	def test_a_refusal_is_reported_in_its_own_words(self):
		self.put(queued_at=time.time())
		self.run_job(MagicMock(side_effect=frappe.ValidationError("Claude declined to read this document.")))
		self.assertEqual(self.state()["error"], "Claude declined to read this document.")

	def test_anything_else_is_logged_and_reported_plainly(self):
		self.put(queued_at=time.time())
		self.run_job(MagicMock(side_effect=KeyError("lines")))
		self.assertEqual((self.state()["status"], self.state()["error"]), ("failed", "failed"))
		jobs.frappe.log_error.assert_called_once()

	def test_a_missing_file_is_said_so(self):
		self.put(queued_at=time.time())
		del self.store[self.job.file_key("T")]
		read = MagicMock()
		self.run_job(read)
		self.assertEqual(self.state()["error"], "missing")
		read.assert_not_called()

	def test_a_reading_given_up_on_is_not_read_after_all(self):
		self.put(queued_at=time.time() - self.job.limit - 1)
		read = MagicMock()
		self.run_job(read)
		read.assert_not_called()
		self.assertEqual((self.state()["status"], self.state()["error"]), ("failed", "lost"))
		self.assertNotIn(self.job.file_key("T"), self.store)
