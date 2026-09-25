"""The way in to Claude: the key, the model, and one call.

Everything this integration sends to Anthropic goes through `create_message`,
which is the Messages API with the site's key and model filled in and every
failure turned into a `ClaudeError`.

The beta endpoint, for server-side fallbacks
--------------------------------------------
The call goes to `client.beta.messages` with `fallbacks="default"`. If the model
declines a request, Anthropic re-runs it on another model inside the same call,
chosen by the kind of refusal, rather than returning nothing. An invoice will
almost never be declined, but when it is, a silent retry is better than an error
the reader cannot act on. A refusal from the whole chain still comes back as
`stop_reason == "refusal"`, and `documents.read` reports that.

One attempt, under the web server's timeout
-------------------------------------------
Reading a scan happens inside the reader's request, so the call has to finish
before gunicorn gives up on that request, which on a bench is 120 seconds. The
SDK retries timeouts, which would double the wait past that point, so
retries are off and the single attempt is given `TIMEOUT`. Overloaded or rate
limited is then an error that says to try again in a minute, which is what a
retry would have done anyway, only visibly.

Nothing is logged with the request in it
----------------------------------------
The request is a scanned invoice, with names, account numbers and amounts on
it. `ClaudeError` carries Anthropic's message and the status, never the
request, and nothing here calls `frappe.log_error` with the call's locals in
scope.
"""

from contextlib import contextmanager

import anthropic
import frappe
from frappe import _

SETTINGS = "Claude Settings"

# The model used when `Claude Settings` names none. Opus rather than Sonnet
# because a misread digit on an invoice costs more than the difference in
# price, which is a few cents a page. A site can choose otherwise in the
# settings.
DEFAULT_MODEL = "claude-opus-5"

# Seconds. Under gunicorn's 120, with room for the rest of the request.
TIMEOUT = 100

BETAS = ["server-side-fallback-2026-07-01"]


class ClaudeError(frappe.ValidationError):
	"""A call Anthropic refused or could not finish, and why, in a sentence.

	A `ValidationError` so the message reaches whoever pressed the button rather
	than becoming a 500. Almost every cause is something a person acts on:
	the key is wrong, the scan is too large, the service is busy.

	`status` is the HTTP status where there was one, and None for a timeout or
	a connection that never got that far.
	"""

	def __init__(self, message: str, status: int | None = None):
		super().__init__(message)
		self.status = status


def fail(message: str, status: int | None = None):
	"""Raise a `ClaudeError` through `frappe.throw`, so the message reaches the
	browser. A bare `raise` puts no message in the response, and the upload
	helper the page sends scans with reads its message from there."""
	frappe.throw(message, exc=ClaudeError(message, status))


def settings() -> dict:
	"""What `Claude Settings` holds, key included.

	Guarded by the doctype's existence, for the window between code landing and
	the migrate that creates the Single. That reads as unconfigured, not as an
	error. See `commons.api_integrations.auth0.client.settings`, which does the
	same for the same reason.
	"""
	if not frappe.db.exists("DocType", SETTINGS, cache=True):
		return {}
	document = frappe.get_cached_doc(SETTINGS)
	return {
		"api_key": (document.get_password("api_key", raise_exception=False) or "").strip(),
		"model": (document.model or "").strip() or DEFAULT_MODEL,
	}


def available() -> bool:
	"""Whether this site has a Claude key to call with.

	Asked by pages that read documents, so that without a key the page leaves
	itself out rather than failing after somebody has uploaded something.
	"""
	return bool(settings().get("api_key"))


def model() -> str:
	return settings().get("model") or DEFAULT_MODEL


def create_message(**params):
	"""One Messages API call with the site's key and model, or a `ClaudeError`.

	`params` is everything but the model, the betas and the fallbacks, which
	this function supplies. Returns the SDK's `BetaMessage`.
	"""
	held = _held()
	with _errors(held["model"]):
		return _client(held, TIMEOUT).beta.messages.create(
			model=held["model"], betas=BETAS, fallbacks="default", **params
		)


def stream_message(on_text=None, timeout: float = TIMEOUT, **params):
	"""The same call, streamed, for work done outside a web request.

	A background job has no gunicorn limit to stay under, so it can give the
	call a longer `timeout` and a larger `max_tokens`, and streaming keeps the
	connection alive while a long answer is written. `on_text` is called with
	each piece of text as it arrives, which is how a job reports progress.
	Returns the SDK's final `BetaMessage`, exactly as `create_message` would.
	"""
	held = _held()
	with _errors(held["model"]):
		with _client(held, timeout).beta.messages.stream(
			model=held["model"], betas=BETAS, fallbacks="default", **params
		) as stream:
			if on_text:
				for text in stream.text_stream:
					on_text(text)
			return stream.get_final_message()


def _held() -> dict:
	held = settings()
	if not held.get("api_key"):
		fail(_("Claude is not set up on this site. Add an API key in Claude Settings."))
	return held


def _client(held: dict, timeout: float):
	return anthropic.Anthropic(api_key=held["api_key"], timeout=timeout, max_retries=0)


@contextmanager
def _errors(model_name: str):
	"""Every way the call can fail, as a `ClaudeError` a person can read."""
	try:
		yield
	except anthropic.AuthenticationError:
		fail(_("Anthropic did not accept the API key in Claude Settings."), 401)
	except anthropic.PermissionDeniedError:
		fail(_("The API key in Claude Settings is not allowed to use {0}.").format(model_name), 403)
	except anthropic.NotFoundError:
		fail(
			_("Anthropic has no model called {0}. Check the model in Claude Settings.").format(model_name),
			404,
		)
	except anthropic.RateLimitError:
		fail(_("Claude is handling too many requests from this site. Try again in a minute."), 429)
	except anthropic.BadRequestError as error:
		# Usually the document itself: too large, too many pages, or not
		# something the API can open. Anthropic's own words say which.
		fail(_("Claude could not take that document: {0}").format(error.message), 400)
	except anthropic.APITimeoutError:
		fail(_("Claude took too long to read that. Try again, or scan fewer pages at a time."))
	except anthropic.APIConnectionError:
		fail(_("This site could not reach Anthropic. Try again in a minute."))
	except anthropic.APIStatusError as error:
		# 5xx and 529 (overloaded). Nothing the reader did.
		fail(
			_("Claude is unavailable at the moment ({0}). Try again in a minute.").format(error.status_code),
			error.status_code,
		)
