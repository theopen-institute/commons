"""That every module this app declares is one migrate can actually import.

`sync_module_defs` writes a `Module Def` for each line of `modules.txt`, and
`frappe.model.sync.sync_for` then resolves each of those names by importing
`commons.<scrubbed module>` with no existence guard. A line with no package
under it therefore does not degrade -- it fails migrate outright, for the whole
site, at a point that names the module rather than the file that is missing.

The reverse is just as quiet the other way: a package under `commons/` that
looks like a module and is not declared is never synced, and its `doctype/`
folder is simply never looked in.

Neither fails where it is caused, so both are pinned here. There is nothing
site-connected about either -- they are two directory listings and a file.
"""

import importlib
import os
import unittest
from unittest import TestCase

from commons.commons_core import install

APP_ROOT = os.path.dirname(os.path.dirname(install.__file__))


def declared() -> list[str]:
	"""The modules named in `modules.txt`, in file order."""
	with open(os.path.join(APP_ROOT, "modules.txt"), encoding="utf-8") as handle:
		return [line.strip() for line in handle if line.strip()]


class TestDeclaredModules(TestCase):
	def test_modules_txt_is_not_empty(self):
		"""Guards the two tests below, which pass vacuously over nothing."""
		self.assertTrue(declared())

	def test_every_declared_module_has_a_package_to_import(self):
		"""`frappe.model.sync.sync_for` imports it with no existence guard."""
		import frappe

		for module in declared():
			with self.subTest(module=module):
				importlib.import_module(f"{install.APP}.{frappe.scrub(module)}")

	def test_every_module_package_is_declared(self):
		"""The other direction: a package with doctypes under it must be named.

		A module directory this app ships and `modules.txt` does not name is
		one the doctype sync never walks, so its doctypes are never created and
		nothing says so.
		"""
		import frappe

		names = {frappe.scrub(module) for module in declared()}
		for entry in sorted(os.listdir(APP_ROOT)):
			path = os.path.join(APP_ROOT, entry)
			if not os.path.isdir(os.path.join(path, "doctype")):
				continue
			with self.subTest(package=entry):
				self.assertIn(entry, names, f"{entry}/ has doctypes but is not in modules.txt")


class TestRetiredAppIsGone(TestCase):
	"""NepalERP left nothing behind that this app still has to carry.

	The app was retired, its two modules were taken over so that uninstalling it
	would not delete the site's own records, and both halves of that have now
	been settled: `Education Extensions` is this app's module and keeps its
	name, and `NepalERP` was emptied -- `Prize` and `Prize Submission` moved to
	`Education Extensions`, `Approval` and `User Link` to `Commons Core` -- and
	then deleted.

	This is the one thing that would not be obvious from the tree if it came
	back: a `modules.txt` line reintroducing an empty module named after
	somebody else's app.
	"""

	def test_nepalerp_is_not_declared(self):
		self.assertNotIn("NepalERP", declared())

	def test_nepalerp_has_no_package(self):
		self.assertFalse(os.path.isdir(os.path.join(APP_ROOT, "nepalerp")))


if __name__ == "__main__":
	unittest.main()
