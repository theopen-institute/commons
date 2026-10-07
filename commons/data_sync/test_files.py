"""Which attach values Data Sync treats as this site's files, site-less.

Writing, reusing and renaming files through `apply` was checked on
register.localhost: a free name kept, the same content reused, other content
under the name saved anew with the record pointed at it, and a snapshot's files.
"""

from unittest import TestCase

from commons.data_sync import files


class TestFileUrls(TestCase):
	def test_site_files(self):
		self.assertEqual(files._parse("/files/logo.svg"), ("logo.svg", 0))
		self.assertEqual(files._parse("/private/files/scan.pdf"), ("scan.pdf", 1))

	def test_anything_else_stays_a_value(self):
		for url in (
			None,
			"",
			"https://example.com/files/logo.svg",
			"/assets/commons/icons/x.svg",
			"/files/",
			"/files/../site_config.json",
			"/files/sub/logo.svg",
			"/private/files/..",
		):
			self.assertIsNone(files._parse(url), url)
