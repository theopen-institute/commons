"""Adopting a retired app's modules, which is the one thing here that can lose data.

`commons.install.adopt` is a single field update, and every assertion below is
about the cases in which it must *not* run. A module taken from an app that
still ships it would be quietly stolen; a module created rather than adopted
would put someone else's retired app in the module list of every site running
this one. Neither fails loudly, so both are pinned.
"""

from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from commons import install


class TestAdopt(TestCase):
	def adopt(self, owners):
		"""`adopt()` over a site whose `Module Def` rows say `owners`.

		Returns what it wrote, as {module: app_name}. `frappe.db` is replaced
		whole rather than patched into: site-less there is no connection behind
		the proxy for an attribute to come from.
		"""
		written = {}

		def get_value(doctype, name, field):
			self.assertEqual(doctype, "Module Def")
			return owners.get(name)

		def set_value(doctype, name, field, value):
			written[name] = value

		# `install` imports frappe inside the function, so the stand-in goes on
		# the frappe module itself rather than on an attribute of `install`,
		# which never holds one.
		import frappe

		database = SimpleNamespace(get_value=get_value, set_value=set_value)
		with patch.object(frappe, "db", database):
			install.adopt()
		return written

	def test_a_module_the_retired_app_still_owns_is_taken(self):
		written = self.adopt({"NepalERP": "nepalerp", "Education Extensions": "nepalerp"})
		self.assertEqual(written, {"NepalERP": install.APP, "Education Extensions": install.APP})

	def test_a_site_that_never_had_the_retired_app_is_untouched(self):
		"""No `Module Def`, so nothing to adopt and nothing created."""
		self.assertEqual(self.adopt({}), {})

	def test_running_twice_writes_nothing_the_second_time(self):
		self.assertEqual(self.adopt({name: install.APP for name in install.ABSORBED_FROM}), {})

	def test_a_module_another_app_owns_is_left_alone(self):
		"""The narrowness that matters.

		A module is taken only from the app it is named as belonging to. Were
		this a bare "does this app own it" test, a module some *other* app was
		still shipping would be claimed out from under it -- silently, since
		nothing about a `Module Def` says who is using it.
		"""
		written = self.adopt({"NepalERP": "someone_else", "Education Extensions": "education"})
		self.assertEqual(written, {})


class TestAbsorbedModulesAreNotCreated(TestCase):
	"""The absorbed modules are adopted where they exist and created nowhere.

	`add_module_defs` walks the whole of `modules.txt`, so using it would give
	every site running this app two empty modules named after a retired one.
	`sync_module_defs` skips them for exactly that reason; this pins the list it
	skips against the list it adopts, which is the pair that has to agree.
	"""

	def test_every_absorbed_module_is_declared_in_modules_txt(self):
		"""Or `Workspace.validate` throws: `app` comes from `get_module_app`."""
		import os

		path = os.path.join(os.path.dirname(install.__file__), "modules.txt")
		with open(path, encoding="utf-8") as handle:
			declared = {line.strip() for line in handle if line.strip()}
		for module in install.ABSORBED_FROM:
			self.assertIn(module, declared)

	def test_every_absorbed_module_has_a_package_to_import(self):
		"""`frappe.model.sync.sync_for` imports it with no existence guard."""
		import importlib

		import frappe

		for module in install.ABSORBED_FROM:
			importlib.import_module(f"{install.APP}.{frappe.scrub(module)}")
