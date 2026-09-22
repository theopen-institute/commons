# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The shape of what `make_qr_code` hands a template.

There is not much to a four-line wrapper, and what there is, is a contract this
app does not get to change. Print formats on live sites were written against the
retired NepalERP app's version and put the result straight into an `<img src>`,
so the prefix, the encoding and the image format are all load-bearing for
templates nobody here is going to re-read before a release. These pin them.

The last one pins that the argument reaches the image at all -- a wrapper that
ignored `data` and returned a constant would pass every other assertion here.
"""

import base64
import io
from unittest import TestCase

from commons.commons_core.jinja import make_qr_code

PREFIX = "data:image/png;base64,"


class TestMakeQrCode(TestCase):
	def png(self, data):
		"""The decoded PNG behind the URI, asserting the URI on the way through."""
		uri = make_qr_code(data)
		self.assertTrue(uri.startswith(PREFIX), uri[:40])

		return base64.b64decode(uri.removeprefix(PREFIX), validate=True)

	def test_is_a_png(self):
		self.assertEqual(self.png("https://example.com/invoice/1")[:8], b"\x89PNG\r\n\x1a\n")

	def test_opens_as_an_image(self):
		from PIL import Image

		# Pillow arrives with the `pil` extra `pyproject.toml` asks for, and is
		# what `qrcode.make()` drew with in the first place -- so this is a
		# round trip through the bytes, not a second opinion on the encoder.
		with Image.open(io.BytesIO(self.png("https://example.com/invoice/1"))) as img:
			self.assertEqual(img.format, "PNG")

	def test_no_argument_still_renders(self):
		"""The default is `""`, and an empty QR code is a valid one."""
		self.assertEqual(make_qr_code(), make_qr_code(""))
		self.assertEqual(self.png("")[:8], b"\x89PNG\r\n\x1a\n")

	def test_data_reaches_the_image(self):
		self.assertNotEqual(self.png("one"), self.png("two"))
