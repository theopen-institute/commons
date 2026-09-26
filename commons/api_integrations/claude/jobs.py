"""Reading a document in a background job, and asking after it.

A read by Claude can outlast a web request: a long statement takes minutes, and
even one invoice can take a worker's full minute and a half. So the endpoint
that takes the file answers at once with a token, a job in the `long` queue does
the reading, and the browser asks after the token every few seconds. `Job` is
the plumbing both callers share, Document Capture's invoices and the bank
statement import, so that neither has its own copy of the rules below.

The state lives in the cache
----------------------------
Under the token: `queued`, then `reading` (with whatever progress the caller
reports), then `done` with the result or `failed` with a sentence. The file
waits in the cache beside it and is dropped as soon as the job has read it.
Nothing is stored in the database: a reading is worth keeping only until the
person who asked for it has it.

Only the person who started it may ask
--------------------------------------
The state records the starter, and `status` refuses anybody else as though the
token did not exist. The result is what Claude read off somebody's invoice or
bank statement, and the token is the only thing standing between it and
another user who guessed or overheard it.

A job that died
---------------
RQ kills a job that runs past its timeout, and a worker can die outright. In
either case nothing writes `failed`, and the state would say `reading` until the
cache let it go an hour later, with the browser asking all that time. So the
state carries when the job was queued and when it started, and `status` reports
a reading as failed once it has run longer than the job was allowed to
(`timeout` and a margin), or waited in the queue that long. The job itself
checks the same thing before it starts, so a reading the browser has given up
on is not read, and billed, after all.
"""

import time

import frappe
from frappe import _

# How long a finished or abandoned reading is kept for the browser to collect.
STATE_TTL = 3600

# Seconds past a job's timeout before `status` gives up on it: long enough for
# RQ to notice and for the job's last write to land, short enough that nobody
# waits long on a job that is gone.
MARGIN = 60

# Keys a caller may not set through `progress`: they are the plumbing's.
RESERVED = frozenset({"user", "queued_at", "started_at"})


class Job:
	"""One kind of background reading.

	`name` keeps the cache keys apart ("statement_import"), `method` is the
	dotted path of the function the job runs, which should call `run`, and
	`timeout` is the job's RQ timeout in seconds.
	"""

	def __init__(self, name: str, method: str, timeout: int, ttl: int = STATE_TTL):
		self.name = name
		self.method = method
		self.timeout = timeout
		self.ttl = ttl

	@property
	def limit(self) -> int:
		"""Seconds after which a reading still queued, or still reading, is
		taken to be lost."""
		return self.timeout + MARGIN

	def state_key(self, token: str) -> str:
		return f"commons:{self.name}:state:{token}"

	def file_key(self, token: str) -> str:
		return f"commons:{self.name}:file:{token}"

	def start(self, content: bytes, **state) -> str:
		"""Put the file in the cache, queue the job, and return its token.

		`state` is what the browser should see before the job has begun, such as
		a count of zero. Permission checks are the caller's, and come first.
		"""
		token = frappe.generate_hash(length=20)
		frappe.cache.set_value(self.file_key(token), content, expires_in_sec=self.ttl)
		self.save(
			token,
			{
				**state,
				"status": "queued",
				"user": frappe.session.user,
				"queued_at": time.time(),
				"started_at": None,
			},
		)
		frappe.enqueue(self.method, queue="long", timeout=self.timeout, token=token)
		return token

	def status(self, token: str, lost: str) -> dict:
		"""Where a reading has got to, for its starter and nobody else.

		`lost` is the sentence for a job that has run out of time without saying
		how it ended.
		"""
		state = frappe.cache.get_value(self.state_key(token), expires=True)
		if not state or state.get("user") != frappe.session.user:
			frappe.throw(_("That reading is not available. Start it again."), frappe.DoesNotExistError)
		if self.overdue(state):
			state = {**state, "status": "failed", "error": lost}
		return {key: value for key, value in state.items() if key not in RESERVED}

	def overdue(self, state: dict, now: float | None = None) -> bool:
		"""Whether a reading that has not finished never will: running for longer
		than RQ allows it, or waiting in the queue as long. A state without the
		times, written before they were kept, is left to the cache's expiry."""
		if state.get("status") not in ("queued", "reading"):
			return False
		since = state.get("started_at") or state.get("queued_at")
		if not since:
			return False
		return (now or time.time()) - since > self.limit

	def run(self, token: str, read, missing: str, failed: str, lost: str, log_title: str) -> None:
		"""The body of the job: take the file, `read` it, and record the end.

		`read(content, progress)` returns the result, calling
		`progress(**changes)` as it goes. A `frappe.ValidationError` it raises
		is meant for the reader (a `ClaudeError`, a file that cannot be read),
		and its message becomes the error. Anything else is logged, without the
		file, and reported as `failed`. `missing` is the sentence for a file the
		cache no longer has, and `lost` the one `status` has already given for
		a reading that waited too long to start.
		"""
		state = frappe.cache.get_value(self.state_key(token), expires=True) or {}
		if self.overdue(state):
			# The browser has been told this reading failed. Reading it now
			# would bill the site for an answer nobody collects.
			frappe.cache.delete_value(self.file_key(token))
			self.update(token, state, status="failed", error=lost)
			return
		# `expires=True` keeps a copy of up to 20 MB out of the process's local cache.
		content = frappe.cache.get_value(self.file_key(token), expires=True)
		frappe.cache.delete_value(self.file_key(token))
		if content is None:
			self.update(token, state, status="failed", error=missing)
			return
		self.update(token, state, status="reading", started_at=time.time())

		def progress(**changes):
			self.update(token, state, **{key: value for key, value in changes.items() if key not in RESERVED})

		try:
			result = read(content, progress)
		except frappe.ValidationError as error:
			self.update(token, state, status="failed", error=str(error) or failed)
			return
		except Exception:
			# Logged without the document: the traceback, not the request.
			frappe.log_error(title=log_title)
			self.update(token, state, status="failed", error=failed)
			return
		self.update(token, state, status="done", result=result)

	def save(self, token: str, state: dict) -> None:
		frappe.cache.set_value(self.state_key(token), state, expires_in_sec=self.ttl)

	def update(self, token: str, state: dict, **changes) -> None:
		state.update(changes)
		self.save(token, state)


class RowCounter:
	"""Counts the rows in Claude's answer as it streams in.

	Each row is one object with a `key` (by default `"description"`) that
	nothing else in the caller's schema has, so counting that key counts the
	rows. A key split across two pieces of text is caught by keeping the tail
	of the last piece. The count is reported only when it changes, and at most
	once a second, so a fast stream does not write to the cache hundreds of
	times.
	"""

	KEY = '"description"'

	def __init__(self, report, interval: float = 1.0, key: str | None = None):
		self.report = report
		self.interval = interval
		self.key = key or self.KEY
		self.count = 0
		self.reported = 0
		self.tail = ""
		self.last = 0.0

	def feed(self, text: str) -> None:
		window = self.tail + text
		self.count += window.count(self.key) - self.tail.count(self.key)
		self.tail = window[-(len(self.key) - 1) :]
		now = time.monotonic()
		if self.count != self.reported and now - self.last >= self.interval:
			self.report(self.count)
			self.reported = self.count
			self.last = now
