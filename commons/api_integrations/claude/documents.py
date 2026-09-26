"""Reading a scanned document into a JSON schema.

`read` is the whole of it: an image or a PDF goes in with a schema and an
instruction, and a dict in that schema's shape comes out. The schema is
enforced by the API (structured outputs, `output_config.format`), so what comes
back always parses and always has the required keys. Whether the values are
right is a separate question, and it is the caller's to check.

Preparing an image
------------------
A photo off a phone is the common case and the awkward one, for three reasons,
and `prepare` deals with each:

* It is usually sideways. Phones store the pixels as the sensor saw them and
  record the rotation in EXIF, which Anthropic does not read. So the rotation is
  applied first, or Claude is reading an invoice lying on its side.
* It is usually too large. Anthropic refuses images over 5 MB, and a
  12-megapixel photo is often that on its own. Opus 5 reads images at up to
  `MAX_EDGE` pixels on the long edge and scales anything larger down itself, so
  scaling to that edge here loses nothing and brings the file well under the
  limit.
* It may be in a format the API does not take, HEIC above all. Pillow cannot
  open HEIC either, so that one is refused with a sentence saying what to send
  instead. On an iPhone, a browser's file picker normally converts to JPEG
  before the file leaves the phone, so this is rarer than it sounds.

And an image can be far larger once opened than it is as a file. Pillow refuses
one of more than twice `Image.MAX_IMAGE_PIXELS` (about 179 megapixels) with a
`DecompressionBombError`, which is not an `OSError`, and a PNG of 20 MB can
unpack into gigabytes. So the size is checked before a pixel is decoded: a JPEG
is decoded straight at a fraction of its size (`draft`), which is how a 108
megapixel phone photo is read without holding it whole, and anything else that
large is refused with a sentence.

A PDF is passed through as it is: the API reads PDFs natively, text layer and
page images both, up to `MAX_BYTES`.
"""

import base64
import io
import json
import math
import warnings

import frappe
from frappe import _

from commons.api_integrations.claude import client

# What a person may send. Above Anthropic's per-image limit because an image is
# scaled down before it goes, and well under its 32 MB request limit for a PDF,
# which is sent as it is.
MAX_BYTES = 20 * 1024 * 1024

# The longest edge Opus 5 reads at. Larger images are scaled down by the API
# anyway, so sending more only costs upload time.
MAX_EDGE = 2576

# Anthropic's per-image limit, which applies after base64 encoding.
MAX_IMAGE_BYTES = 5 * 1024 * 1024

# Pixels an image may have and still be decoded whole: Pillow's own warning
# threshold, about 89 megapixels, or a quarter of a gigabyte once decoded. A
# JPEG above it is decoded at a fraction of its size instead (`_prepare_image`).
MAX_PIXELS = 89_478_485

ORIENTATION = 0x0112  # the EXIF tag a phone records its rotation in

PDF = "application/pdf"
IMAGE_FORMATS = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}


def prepare(content: bytes) -> tuple[bytes, str]:
	"""The document as Anthropic will take it: bytes and a media type.

	Decided by what the bytes are rather than by the name or the type the
	browser sent, both of which are only claims.
	"""
	check(content)
	if content.startswith(b"%PDF"):
		return content, PDF
	return _prepare_image(content)


def check(content: bytes) -> None:
	"""Refuse a file that could never be sent: empty, or over `MAX_BYTES`.

	The first thing `prepare` asks, and what an endpoint that hands the file to
	a background job asks before it does, so that the answer comes at once and
	twenty megabytes of nothing are not queued.
	"""
	if not content:
		frappe.throw(_("That file is empty."))
	if len(content) > MAX_BYTES:
		frappe.throw(_("That file is over {0} MB. Send a smaller scan.").format(MAX_BYTES // (1024 * 1024)))


def _prepare_image(content: bytes) -> tuple[bytes, str]:
	from PIL import Image, ImageOps, UnidentifiedImageError

	too_large = _("That image is too large to read. Send a smaller photo, or a PDF.")
	try:
		# Pillow warns between one and two times its limit and raises above it.
		# The warning is this function's to act on, below; the error is caught.
		with warnings.catch_warnings():
			warnings.simplefilter("ignore", Image.DecompressionBombWarning)
			image = Image.open(io.BytesIO(content))
		original_size = image.size
		if original_size[0] * original_size[1] > MAX_PIXELS:
			if image.format != "JPEG":
				frappe.throw(too_large)
			# Decoded at a half, a quarter or an eighth, whichever keeps the
			# long edge at `MAX_EDGE` or more. Only a JPEG decoder can do that.
			long_edge = max(original_size)
			image.draft(
				image.mode,
				tuple(max(1, math.ceil(side * MAX_EDGE / long_edge)) for side in original_size),
			)
		image.load()
	except Image.DecompressionBombError:
		frappe.throw(too_large)
	except (UnidentifiedImageError, OSError):
		frappe.throw(_("That is not an image or a PDF this site can read. Send a JPEG, PNG or PDF."))

	source_format = image.format
	drafted = image.size != original_size
	# Read off the tag rather than off `exif_transpose`, which returns a copy
	# whether or not it turned anything.
	rotated = image.getexif().get(ORIENTATION, 1) != 1
	upright = ImageOps.exif_transpose(image)
	resized = max(upright.size) > MAX_EDGE
	if resized:
		upright.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)

	fits = len(base64.b64encode(content)) <= MAX_IMAGE_BYTES
	if source_format in IMAGE_FORMATS and not rotated and not resized and not drafted and fits:
		return content, IMAGE_FORMATS[source_format]

	# Anything changed is re-encoded as JPEG. That is what a scan of paper wants
	# and it is the smallest of the four formats the API takes.
	buffer = io.BytesIO()
	upright.convert("RGB").save(buffer, format="JPEG", quality=90)
	return buffer.getvalue(), "image/jpeg"


def read(
	content: bytes,
	schema: dict,
	instructions: str,
	effort: str = "medium",
	on_text=None,
	timeout: float | None = None,
	max_tokens: int = 16000,
	too_long: str | None = None,
) -> dict:
	"""What the document says, in the shape of `schema`.

	`on_text`, `timeout` and `max_tokens` are for a background job:
	see `client.stream_message`.

	`too_long` is the sentence to show when the answer does not fit in
	`max_tokens`, which only the caller can put in terms of what it reads: one
	invoice at a time, fewer pages of a statement.

	`effort` is the Messages API's. Medium rather than the default high because
	copying figures off a page is not hard reasoning, and a lower effort is a
	shorter wait. Raise it for documents that come back wrong.

	Raises `ClaudeError` when nothing usable came back: the model declined, or
	the answer did not fit in `max_tokens`, which for an invoice means a document
	far longer than one invoice.
	"""
	data, media_type = prepare(content)
	encoded = base64.standard_b64encode(data).decode()
	source = {"type": "base64", "media_type": media_type, "data": encoded}
	block = (
		{"type": "document", "source": source} if media_type == PDF else {"type": "image", "source": source}
	)

	params = {
		"max_tokens": max_tokens,
		"output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
		"messages": [{"role": "user", "content": [block, {"type": "text", "text": instructions}]}],
	}
	# Streamed when the caller is a background job that reports progress or
	# needs longer than a web request allows; otherwise the plain call.
	if on_text or timeout:
		response = client.stream_message(on_text=on_text, timeout=timeout or client.TIMEOUT, **params)
	else:
		response = client.create_message(**params)

	if response.stop_reason == "refusal":
		client.fail(_("Claude declined to read this document."))
	if response.stop_reason == "max_tokens":
		client.fail(too_long or _("That document is too long to read in one go."))

	text = next((block.text for block in response.content if block.type == "text"), None)
	if text is None:
		client.fail(_("Claude sent back nothing to read."))
	return json.loads(text)
