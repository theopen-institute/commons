"""What a scan is turned into before it is sent, and what comes back.

Site-less. The call to Anthropic is replaced by a stand-in for
`client.create_message`, so what is under test is this app's half: the image
arrives upright and inside Anthropic's limits, the request asks for the schema,
and a refusal or a truncated answer becomes an error rather than half an
invoice.
"""

import io
import logging
from types import SimpleNamespace
from typing import ClassVar
from unittest import TestCase
from unittest.mock import patch

import anthropic
import httpx2
from PIL import Image

from commons.api_integrations.claude import client, documents

_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def _throw(message, exc=None, **kwargs):
	"""`frappe.throw` without the message log, which needs a site. An instance
	is raised as it is, so a `ClaudeError`'s status survives; anything else
	becomes a `ValueError` to assert on."""
	if isinstance(exc, Exception):
		raise exc
	raise ValueError(message)


_throw_patch = patch("frappe.throw", _throw)


def setUpModule():
	_logger.start()
	_throw_patch.start()


def tearDownModule():
	_throw_patch.stop()
	_logger.stop()


def image(size=(800, 600), format="JPEG", orientation=None) -> bytes:
	picture = Image.new("RGB", size, "white")
	buffer = io.BytesIO()
	if orientation:
		exif = Image.Exif()
		exif[documents.ORIENTATION] = orientation
		picture.save(buffer, format=format, exif=exif)
	else:
		picture.save(buffer, format=format)
	return buffer.getvalue()


def size_of(content: bytes) -> tuple[int, int]:
	return Image.open(io.BytesIO(content)).size


class TestPreparing(TestCase):
	def test_a_pdf_goes_as_it_is(self):
		pdf = b"%PDF-1.7\n..."
		self.assertEqual(documents.prepare(pdf), (pdf, "application/pdf"))

	def test_a_small_upright_image_goes_as_it_is(self):
		for format, media_type in (("JPEG", "image/jpeg"), ("PNG", "image/png")):
			with self.subTest(format=format):
				content = image(format=format)
				self.assertEqual(documents.prepare(content), (content, media_type))

	def test_a_large_photo_is_scaled_to_the_models_edge(self):
		content, media_type = documents.prepare(image(size=(4000, 3000)))
		self.assertEqual(media_type, "image/jpeg")
		self.assertEqual(max(size_of(content)), documents.MAX_EDGE)

	def test_a_sideways_photo_arrives_upright(self):
		"""Orientation 6 is a phone held upright: the pixels are landscape and
		the tag says to turn them a quarter."""
		content, _media_type = documents.prepare(image(size=(800, 600), orientation=6))
		self.assertEqual(size_of(content), (600, 800))

	def test_a_format_the_api_does_not_take_is_converted(self):
		content, media_type = documents.prepare(image(format="BMP"))
		self.assertEqual(media_type, "image/jpeg")
		self.assertEqual(size_of(content), (800, 600))

	def test_something_else_is_refused(self):
		with self.assertRaisesRegex(ValueError, "JPEG, PNG or PDF"):
			documents.prepare(b"PK\x03\x04 a zip file")

	def test_nothing_is_refused(self):
		with self.assertRaisesRegex(ValueError, "empty"):
			documents.prepare(b"")

	def test_too_large_is_refused_before_it_is_opened(self):
		with self.assertRaisesRegex(ValueError, "over 20 MB"):
			documents.prepare(b"%PDF" + b"0" * documents.MAX_BYTES)


def response(stop_reason="end_turn", text='{"total": 11300}'):
	content = [SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)]
	return SimpleNamespace(stop_reason=stop_reason, content=content)


class TestReading(TestCase):
	SCHEMA: ClassVar = {"type": "object", "properties": {"total": {"type": "number"}}}

	def read(self, content: bytes, answer=None):
		with patch.object(documents.client, "create_message", return_value=answer or response()) as call:
			result = documents.read(content, self.SCHEMA, "Copy the total.")
		return result, call.call_args.kwargs

	def test_asks_for_the_schema_and_returns_what_it_says(self):
		result, sent = self.read(image())
		self.assertEqual(result, {"total": 11300})
		self.assertEqual(sent["output_config"]["format"], {"type": "json_schema", "schema": self.SCHEMA})

	def test_an_image_is_an_image_block_and_a_pdf_a_document(self):
		for content, kind in ((image(), "image"), (b"%PDF-1.7", "document")):
			with self.subTest(kind=kind):
				_result, sent = self.read(content)
				blocks = sent["messages"][0]["content"]
				self.assertEqual(blocks[0]["type"], kind)
				self.assertEqual(blocks[1], {"type": "text", "text": "Copy the total."})

	def test_a_refusal_is_an_error(self):
		with self.assertRaisesRegex(client.ClaudeError, "declined"):
			self.read(image(), response(stop_reason="refusal", text="{}"))

	def test_a_cut_off_answer_is_an_error_not_half_an_invoice(self):
		with self.assertRaisesRegex(client.ClaudeError, "too long"):
			self.read(image(), response(stop_reason="max_tokens", text='{"tot'))


def status_error(cls, status):
	request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
	return cls("refused", response=httpx2.Response(status, request=request), body=None)


class TestTheCall(TestCase):
	def call(self, raised):
		fake = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(create=None)))

		def create(**params):
			raise raised

		fake.beta.messages.create = create
		with (
			patch.object(client, "settings", return_value={"api_key": "sk-test", "model": "claude-opus-5"}),
			patch.object(client.anthropic, "Anthropic", return_value=fake),
		):
			client.create_message(messages=[])

	def test_no_key_is_an_error_before_anything_is_sent(self):
		with (
			patch.object(client, "settings", return_value={}),
			patch.object(client.anthropic, "Anthropic") as made,
		):
			with self.assertRaisesRegex(client.ClaudeError, "Claude Settings"):
				client.create_message(messages=[])
		made.assert_not_called()

	def test_refusals_say_what_to_do_and_keep_their_status(self):
		cases = (
			(anthropic.AuthenticationError, 401, "did not accept the API key"),
			(anthropic.RateLimitError, 429, "Try again in a minute"),
			(anthropic.BadRequestError, 400, "could not take that document"),
			(anthropic.InternalServerError, 500, "unavailable"),
		)
		for cls, status, words in cases:
			with self.subTest(status=status):
				with self.assertRaisesRegex(client.ClaudeError, words) as caught:
					self.call(status_error(cls, status))
				self.assertEqual(caught.exception.status, status)

	def test_a_timeout_says_so(self):
		request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
		with self.assertRaisesRegex(client.ClaudeError, "too long"):
			self.call(anthropic.APITimeoutError(request=request))

	def test_the_request_asks_for_fallbacks_and_makes_one_attempt(self):
		sent = {}
		fake = SimpleNamespace(
			beta=SimpleNamespace(messages=SimpleNamespace(create=lambda **params: sent.update(params)))
		)
		with (
			patch.object(client, "settings", return_value={"api_key": "sk-test", "model": "claude-opus-5"}),
			patch.object(client.anthropic, "Anthropic", return_value=fake) as made,
		):
			client.create_message(messages=[])
		self.assertEqual(made.call_args.kwargs["max_retries"], 0)
		self.assertEqual(sent["fallbacks"], "default")
		self.assertEqual(sent["betas"], client.BETAS)
		self.assertEqual(sent["model"], "claude-opus-5")


class TestAvailable(TestCase):
	def test_needs_a_key(self):
		for held, expected in (({}, False), ({"api_key": ""}, False), ({"api_key": "sk"}, True)):
			with self.subTest(held=held), patch.object(client, "settings", return_value=held):
				self.assertEqual(client.available(), expected)
