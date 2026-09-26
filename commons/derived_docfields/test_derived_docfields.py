"""Derived fields against a real site: bench --site SITE execute commons.derived_docfields.test_derived_docfields.run

Rollback-only. The fields are real Custom Fields on ToDo, created inside each
test's savepoint with core's `in_create_custom_fields` flag set -- the flag core
sets for its own bulk installs, which skips the `updatedb` that would otherwise
commit. A derived field has no column for it to create anyway. What does outlive
a rollback is cache: the definitions (process-local and in redis), ToDo's meta
and the Commons Settings document are all dropped again in `tearDown`, so no
other process on the bench sees a field these tests made.

ToDo is the host because it has everything a path can take: two Links to the
same doctype (`allocated_to` and `assigned_by`, both User), a Link onward from
there (User.language), and a Dynamic Link (`reference_type`/`reference_name`).
Its permission rules show a user only the ToDos allocated to or assigned by
them, which is what gives the reader here something to read.

The reader holds no role that can open User or Role -- the point of the suite's
permission tests is that they still see what those derived fields show.
"""

import unittest
from unittest.mock import patch

import frappe
from frappe.database import query as core_query

from commons import testing
from commons.commons_core import settings
from commons.derived_docfields import install, registry, validation
from commons.derived_docfields.engine import DerivedEngine, alias

HOST = "ToDo"
READER = "derived-docfields-reader@example.com"
READER_NAME = "Derived Reader"
LANGUAGE = "af"

FIELDS = (
	# fieldname, fieldtype, derived_from, extra
	("dd_allocated_name", "Data", "allocated_to.full_name", {}),
	("dd_assigner_name", "Data", "assigned_by.full_name", {}),
	("dd_allocated_language", "Link", "allocated_to.language", {"options": "Language"}),
	("dd_language_name", "Data", "dd_allocated_language.language_name", {}),
	("dd_reference_created", "Datetime", "reference_name.creation", {"derived_from_doctypes": "User\nRole"}),
	("dd_secret", "Data", "allocated_to.full_name", {"permlevel": 1}),
	("dd_wild", "Data", "assigned_by.full_name", {"derived_in_wildcard": 1}),
)


def define(fieldname, fieldtype, derived_from, **extra):
	"""A derived Custom Field on ToDo, without the commit a Custom Field save makes."""
	frappe.flags.in_create_custom_fields = True
	try:
		doc = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": extra.pop("dt", HOST),
				"fieldname": fieldname,
				"label": fieldname.replace("_", " ").title(),
				"fieldtype": fieldtype,
				"derived_from": derived_from,
				"insert_after": "description",
				**extra,
			}
		).insert()
	finally:
		frappe.flags.in_create_custom_fields = False
	frappe.clear_cache(doctype=doc.dt)
	return doc


def switch(on: bool) -> None:
	frappe.db.set_single_value(settings.SETTINGS, settings.ENABLE_DERIVED_DOCFIELDS, int(on))
	frappe.clear_document_cache(settings.SETTINGS, settings.SETTINGS)


def forget() -> None:
	"""Drop every cache a test's fields could have reached."""
	registry.clear()
	frappe.clear_cache(doctype=HOST)
	frappe.clear_cache(doctype="User")
	frappe.clear_cache(doctype="Has Role")
	frappe.clear_document_cache(settings.SETTINGS, settings.SETTINGS)


@testing.site_suite()
class TestDerivedDocfields(unittest.TestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install()
		cls._original_user = frappe.session.user

	@classmethod
	def tearDownClass(cls):
		frappe.set_user(cls._original_user)
		super().tearDownClass()

	def setUp(self):
		frappe.set_user("Administrator")
		frappe.db.savepoint("derived_docfields_test")
		# A cleanup rather than tearDown, which is skipped when setUp fails --
		# a lock wait while other suites run on the site, say. The records made
		# so far would stay in the transaction, and the runner commits at the end.
		self.addCleanup(self.undo)
		frappe.flags.mute_emails = True
		switch(on=True)

		reader = frappe.get_doc(
			{
				"doctype": "User",
				"email": READER,
				"first_name": "Derived",
				"last_name": "Reader",
				"language": LANGUAGE,
				"user_type": "System User",
				"send_welcome_email": 0,
			}
		).insert(ignore_permissions=True)
		self.reader = reader.name
		for fieldname, fieldtype, derived_from, extra in FIELDS:
			define(fieldname, fieldtype, derived_from, **dict(extra))

		# Allocated to the reader, assigned by Administrator, about a Role.
		self.mine = self.todo(
			"mine",
			allocated_to=self.reader,
			assigned_by="Administrator",
			reference_type="Role",
			reference_name="System Manager",
		)
		# The other way round, and about a User.
		self.theirs = self.todo(
			"theirs",
			allocated_to="Administrator",
			assigned_by=self.reader,
			reference_type="User",
			reference_name=self.reader,
		)

	def undo(self):
		frappe.set_user("Administrator")
		frappe.db.rollback(save_point="derived_docfields_test")
		frappe.flags.mute_emails = False
		forget()

	def todo(self, description, **values):
		return (
			frappe.get_doc({"doctype": HOST, "description": f"derived test {description}", **values})
			.insert(ignore_permissions=True)
			.name
		)

	def rows(self, fields, **kwargs):
		kwargs.setdefault("filters", {"description": ("like", "derived test %")})
		return {row.name: row for row in frappe.get_all(HOST, fields=["name", *fields], **kwargs)}

	# Reading
	# -------

	def test_a_derived_field_reads_its_linked_value(self):
		rows = self.rows(["dd_allocated_name"])
		self.assertEqual(rows[self.mine].dd_allocated_name, READER_NAME)
		self.assertEqual(rows[self.theirs].dd_allocated_name, "Administrator")

	def test_two_links_to_one_doctype_are_joined_separately(self):
		"""Core's own dotted notation would join User once and read both from it."""
		row = self.rows(["dd_allocated_name", "dd_assigner_name"])[self.mine]
		self.assertEqual((row.dd_allocated_name, row.dd_assigner_name), (READER_NAME, "Administrator"))

	def test_a_path_can_follow_a_derived_link(self):
		row = self.rows(["dd_allocated_language", "dd_language_name"])[self.mine]
		self.assertEqual(row.dd_allocated_language, LANGUAGE)
		self.assertEqual(row.dd_language_name, frappe.db.get_value("Language", LANGUAGE, "language_name"))

	def test_a_dynamic_link_reads_from_whichever_doctype_the_row_names(self):
		rows = self.rows(["dd_reference_created"])
		self.assertEqual(
			rows[self.mine].dd_reference_created, frappe.db.get_value("Role", "System Manager", "creation")
		)
		self.assertEqual(
			rows[self.theirs].dd_reference_created, frappe.db.get_value("User", self.reader, "creation")
		)

	def test_a_dynamic_link_to_an_unlisted_doctype_reads_as_empty(self):
		other = self.todo("other", reference_type="Language", reference_name=LANGUAGE)
		self.assertIsNone(self.rows(["dd_reference_created"])[other].dd_reference_created)

	def test_a_path_can_continue_past_a_dynamic_link(self):
		"""The next join is on the COALESCE of the candidates, and still finds its row."""
		define("dd_reference_owner", "Link", "reference_name.owner", derived_from_doctypes="User\nRole")
		define("dd_reference_owner_name", "Data", "dd_reference_owner.full_name")
		rows = self.rows(["dd_reference_owner_name"])
		for todo, (doctype, name) in {
			self.mine: ("Role", "System Manager"),
			self.theirs: ("User", self.reader),
		}.items():
			owner = frappe.db.get_value(doctype, name, "owner")
			self.assertEqual(
				rows[todo].dd_reference_owner_name, frappe.db.get_value("User", owner, "full_name")
			)
		sql = frappe.get_all(HOST, fields=["dd_reference_owner_name"], run=0).get_sql()
		self.assertIn("COALESCE(", sql.split(" ON ")[-1])

	def test_every_way_of_naming_the_field_reads_the_same(self):
		row = frappe.get_all(
			HOST,
			fields=[
				"name",
				"`tabToDo`.`dd_allocated_name`",
				"tabToDo.dd_assigner_name",
				"dd_allocated_name as who",
			],
			filters={"name": self.mine},
		)[0]
		self.assertEqual(
			(row.dd_allocated_name, row.dd_assigner_name, row.who),
			(READER_NAME, "Administrator", READER_NAME),
		)

	def test_as_list_keeps_the_order_asked_for(self):
		"""Permissions are applied in runs around derived fields; positions must survive that."""
		frappe.set_user(self.reader)
		row = frappe.get_list(
			HOST,
			fields=["dd_allocated_name", "name", "dd_assigner_name", "description"],
			filters={"name": self.mine},
			as_list=True,
		)[0]
		self.assertEqual(row, (READER_NAME, self.mine, "Administrator", "derived test mine"))

	def test_db_get_value_reads_derived_fields(self):
		self.assertEqual(
			frappe.db.get_value(HOST, self.mine, "dd_language_name"),
			frappe.db.get_value("Language", LANGUAGE, "language_name"),
		)

	# Filtering, sorting, grouping, counting
	# --------------------------------------

	def test_filters_by_equality_and_like(self):
		self.assertEqual(set(self.rows([], filters={"dd_allocated_name": READER_NAME})), {self.mine})
		self.assertEqual(
			set(self.rows([], filters={"dd_assigner_name": ("like", "%Reader%")})), {self.theirs}
		)

	def test_filters_in_list_form_and_or_filters(self):
		self.assertEqual(
			set(self.rows([], filters=[[HOST, "dd_allocated_name", "=", READER_NAME]])), {self.mine}
		)
		found = frappe.get_all(
			HOST,
			or_filters=[["dd_allocated_name", "=", READER_NAME], ["dd_assigner_name", "=", READER_NAME]],
			pluck="name",
		)
		self.assertTrue({self.mine, self.theirs} <= set(found))

	def test_a_filter_on_a_dynamic_link_field(self):
		created = frappe.db.get_value("User", self.reader, "creation")
		self.assertEqual(set(self.rows([], filters={"dd_reference_created": created})), {self.theirs})

	def test_order_by_a_derived_field(self):
		names = frappe.get_all(
			HOST,
			filters={"name": ("in", (self.mine, self.theirs))},
			order_by="dd_allocated_name asc",
			pluck="name",
		)
		self.assertEqual(names, [self.theirs, self.mine])  # "Administrator" < "Derived Reader"
		names = frappe.get_all(
			HOST,
			filters={"name": ("in", (self.mine, self.theirs))},
			order_by="`tabToDo`.`dd_allocated_name` desc",
			pluck="name",
		)
		self.assertEqual(names, [self.mine, self.theirs])

	def test_group_by_a_derived_field(self):
		counts = frappe.get_all(
			HOST,
			filters={"name": ("in", (self.mine, self.theirs))},
			fields=["dd_allocated_name", {"COUNT": "*", "as": "total"}],
			group_by="dd_allocated_name",
			order_by="dd_allocated_name asc",
			as_list=True,
		)
		self.assertEqual(counts, (("Administrator", 1), (READER_NAME, 1)))

	def test_count_with_a_derived_filter(self):
		self.assertEqual(
			frappe.db.count(
				HOST, {"dd_allocated_name": READER_NAME, "description": ("like", "derived test %")}
			),
			1,
		)

	def test_raw_sql_filter_conditions_use_a_subquery(self):
		"""`get_filters_cond` output is spliced into SQL that has no joins to lean on."""
		from frappe.desk.reportview import get_filters_cond

		condition = get_filters_cond(HOST, {"dd_allocated_name": READER_NAME}, [])
		self.assertIn("SELECT", condition)
		found = frappe.db.sql(
			f"select name from `tabToDo` where description like 'derived test %%' {condition}", pluck=True
		)
		self.assertEqual(found, [self.mine])

	def test_delete_filtered_on_a_derived_field_deletes_only_matches(self):
		"""The subquery has to compare as SQL: pypika's own would compare as Python and drop the WHERE."""
		frappe.db.delete(HOST, {"dd_assigner_name": READER_NAME, "description": ("like", "derived test %")})
		self.assertEqual(set(self.rows([])), {self.mine})

	# Wildcard
	# --------

	def test_star_includes_only_fields_opted_in(self):
		row = frappe.get_all(HOST, fields=["*"], filters={"name": self.theirs})[0]
		self.assertEqual(row.dd_wild, READER_NAME)
		self.assertNotIn("dd_assigner_name", row)
		self.assertEqual(row.description, "derived test theirs")

	def test_star_with_permissions_includes_them_too(self):
		frappe.set_user(self.reader)
		row = frappe.get_list(HOST, fields=["*"], filters={"name": self.theirs})[0]
		self.assertEqual(row.dd_wild, READER_NAME)

	# Permissions
	# -----------

	def test_the_reader_cannot_open_the_source_records(self):
		"""The premise of the next test, checked rather than assumed.

		Per record: everyone may open their own User, so the doctype-level
		answer is yes. What the next test shows them is Administrator's.
		"""
		self.assertTrue(frappe.has_permission(HOST, "read", doc=self.mine, user=self.reader))
		self.assertFalse(frappe.has_permission("User", "read", doc="Administrator", user=self.reader))
		self.assertFalse(frappe.has_permission("Role", "read", doc="System Manager", user=self.reader))

	def test_a_reader_sees_derived_values_from_doctypes_they_cannot_read(self):
		frappe.set_user(self.reader)
		rows = {
			row.name: row
			for row in frappe.get_list(
				HOST,
				fields=["name", "dd_allocated_name", "dd_assigner_name", "dd_reference_created"],
				filters={"description": ("like", "derived test %")},
			)
		}
		self.assertEqual(set(rows), {self.mine, self.theirs})
		self.assertEqual(rows[self.mine].dd_assigner_name, "Administrator")
		self.assertIsNotNone(rows[self.mine].dd_reference_created)

	def test_the_host_row_rules_still_apply(self):
		hidden = self.todo("hidden", allocated_to="Administrator", assigned_by="Administrator")
		frappe.set_user(self.reader)
		self.assertNotIn(
			hidden, frappe.get_list(HOST, fields=["name", "dd_allocated_name"], pluck="name", limit=0)
		)

	def test_the_derived_fields_own_permlevel_applies(self):
		frappe.set_user(self.reader)
		row = frappe.get_list(
			HOST, fields=["name", "dd_secret", "dd_allocated_name"], filters={"name": self.mine}
		)[0]
		self.assertNotIn("dd_secret", row)
		self.assertEqual(row.dd_allocated_name, READER_NAME)
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list(HOST, filters={"dd_secret": READER_NAME})
		with self.assertRaises(frappe.PermissionError):
			frappe.get_list(HOST, order_by="dd_secret asc")

	# Staying out of the way
	# ----------------------

	def core_sql(self, **kwargs):
		return core_query.Engine._commons_base().get_query(HOST, **kwargs).get_sql()

	def test_switched_off_every_query_is_cores(self):
		switch(on=False)
		kwargs = dict(
			fields=["name", "dd_allocated_name"], filters={"description": "x"}, order_by="modified desc"
		)
		self.assertEqual(frappe.qb.get_query(HOST, **kwargs).get_sql(), self.core_sql(**kwargs))

	def test_a_doctype_without_derived_fields_gets_cores_query(self):
		kwargs = dict(fields=["name", "full_name"], filters={"enabled": 1})
		self.assertEqual(
			frappe.qb.get_query("User", **kwargs).get_sql(),
			core_query.Engine._commons_base().get_query("User", **kwargs).get_sql(),
		)

	def test_a_query_naming_no_derived_field_gets_cores_query(self):
		kwargs = dict(fields=["name", "description"], filters={"status": "Open"}, order_by="creation desc")
		self.assertEqual(frappe.qb.get_query(HOST, **kwargs).get_sql(), self.core_sql(**kwargs))

	def test_a_broken_path_reads_as_null_and_is_reported_once(self):
		broken = registry.Definition(HOST, "dd_allocated_name", "allocated_to", "no_such_field", (), False)
		definitions = {HOST: {**registry.definitions()[HOST], "dd_allocated_name": broken}}
		with (
			patch.object(registry, "definitions", return_value=definitions),
			patch.object(frappe, "log_error") as log_error,
		):
			from commons.derived_docfields import engine

			engine._reported.clear()
			row = self.rows(["dd_allocated_name", "dd_assigner_name"])[self.mine]
			self.rows(["dd_allocated_name"])
		self.assertIsNone(row.dd_allocated_name)
		self.assertEqual(row.dd_assigner_name, "Administrator")
		self.assertEqual(log_error.call_count, 1)

	def test_install_is_idempotent(self):
		install()
		self.assertIs(core_query.Engine, DerivedEngine)
		self.assertIsNot(DerivedEngine._commons_base, DerivedEngine)

	# Documents
	# ---------

	def test_a_document_reads_its_derived_fields(self):
		doc = frappe.get_doc(HOST, self.mine)
		self.assertEqual(doc.dd_allocated_name, READER_NAME)
		self.assertEqual(doc.get("dd_assigner_name"), "Administrator")
		self.assertEqual(
			doc.as_dict()["dd_language_name"], frappe.db.get_value("Language", LANGUAGE, "language_name")
		)
		self.assertEqual(
			doc.as_dict()["dd_reference_created"], frappe.db.get_value("Role", "System Manager", "creation")
		)

	def test_get_before_any_attribute_read(self):
		"""Core's `get` reads the instance dict, where nothing is until the first read."""
		self.assertEqual(frappe.get_doc(HOST, self.mine).get("dd_allocated_name"), READER_NAME)

	def test_a_new_record_reads_from_its_links(self):
		doc = frappe.new_doc(HOST)
		self.assertIsNone(doc.dd_allocated_name)
		doc.allocated_to = self.reader
		self.assertEqual(doc.dd_allocated_name, READER_NAME)

	def test_changing_a_link_changes_what_it_shows(self):
		doc = frappe.get_doc(HOST, self.mine)
		self.assertEqual(doc.dd_allocated_name, READER_NAME)
		doc.allocated_to = "Administrator"
		self.assertEqual(doc.dd_allocated_name, "Administrator")
		self.assertIsNone(doc.dd_language_name)  # Administrator has no language here

	def lookups(self, read):
		"""The doctypes the document half queried while `read` ran, one entry per query."""
		from collections import Counter

		from commons.derived_docfields import document

		with patch.object(document.frappe, "get_all", wraps=frappe.get_all) as get_all:
			read()
		return Counter(call.args[0] for call in get_all.call_args_list)

	def test_one_query_per_linked_doctype(self):
		"""Both links to User in one query; Language, through the derived Link, in the next round."""
		doc = frappe.get_doc(HOST, self.mine)
		self.assertEqual(
			self.lookups(lambda: (doc.as_dict(), doc.as_dict())), {"User": 1, "Role": 1, "Language": 1}
		)

	def test_child_rows_are_looked_up_together(self):
		roles = frappe.get_all(
			"Role",
			filters={"name": ("not in", ("Administrator", "Guest", "All", "Desk User")), "disabled": 0},
			order_by="name asc",
			limit=3,
			pluck="name",
		)
		self.assertEqual(len(roles), 3)
		define("dd_role_title", "Data", "role.role_name", dt="Has Role", insert_after="role")
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": "derived-docfields-roles@example.com",
				"first_name": "Roles",
				"send_welcome_email": 0,
				"roles": [{"role": role} for role in roles],
			}
		).insert(ignore_permissions=True)

		doc = frappe.get_doc("User", user.name)
		rows = [row for row in doc.roles if row.role in roles]
		titles = {}
		self.assertEqual(
			self.lookups(lambda: titles.update({row.role: row.dd_role_title for row in rows})), {"Role": 1}
		)
		self.assertEqual(titles, {role: frappe.db.get_value("Role", role, "role_name") for role in roles})

	def test_explain_shows_the_join_and_its_plan(self):
		from commons.derived_docfields.diagnostics import explain

		found = explain(HOST, fields=["name", "dd_allocated_name"], order_by="dd_allocated_name asc")
		self.assertIn("LEFT JOIN `tabUser` `dd_allocated_to`", found["sql"])
		self.assertIn("dd_allocated_to", {step.get("table") for step in found["plan"]})
		self.assertTrue(any("Sorts every matching row" in note for note in found["notes"]))

	def test_a_value_the_reader_may_not_see_is_taken_off(self):
		frappe.set_user(self.reader)
		doc = frappe.get_doc(HOST, self.mine)
		doc.apply_fieldlevel_read_permissions()
		self.assertIsNone(doc.as_dict().get("dd_secret"))
		self.assertIsNone(doc.get("dd_secret"))
		self.assertEqual(doc.as_dict()["dd_allocated_name"], READER_NAME)

	def test_saving_ignores_whatever_was_sent_for_a_derived_field(self):
		doc = frappe.get_doc(HOST, self.mine)
		doc.update({"dd_allocated_name": "Somebody Else", "description": "derived test mine, edited"})
		doc.save()
		self.assertEqual(frappe.get_doc(HOST, self.mine).dd_allocated_name, READER_NAME)
		self.assertEqual(doc.as_dict()["dd_allocated_name"], READER_NAME)

	def test_core_field_checks_see_derived_fields_as_empty(self):
		"""A derived Link is not something anyone entered, so it can't fail link validation."""
		doc = frappe.get_doc(HOST, self.mine)
		with patch.object(frappe.db, "get_value", wraps=frappe.db.get_value):
			from commons.derived_docfields import document

			with document.quiet():
				self.assertIsNone(doc.get("dd_allocated_language"))
		self.assertEqual(doc.get("dd_allocated_language"), LANGUAGE)

	def test_a_document_pickles_without_its_derived_values(self):
		import pickle

		doc = frappe.get_doc(HOST, self.mine)
		doc.as_dict()
		copy = pickle.loads(pickle.dumps(doc))
		self.assertIs(type(copy), type(doc))
		self.assertNotIn("dd_allocated_name", copy.__dict__)
		self.assertEqual(copy.dd_allocated_name, READER_NAME)

	def test_cached_and_lazy_documents(self):
		import pickle

		self.assertEqual(frappe.get_cached_doc(HOST, self.mine).dd_allocated_name, READER_NAME)
		lazy = frappe.get_lazy_doc(HOST, self.mine)
		self.assertEqual(lazy.dd_allocated_name, READER_NAME)
		self.assertEqual(pickle.loads(pickle.dumps(lazy)).dd_allocated_name, READER_NAME)

	def test_switched_off_a_document_shows_nothing(self):
		switch(on=False)
		doc = frappe.get_doc(HOST, self.mine)
		self.assertIsNone(doc.as_dict()["dd_allocated_name"])

	def test_the_form_asks_again_when_a_link_changes(self):
		from commons.derived_docfields.api import resolve

		frappe.set_user(self.reader)
		values = frappe.get_doc(HOST, self.mine).as_dict()
		values["allocated_to"] = "Administrator"
		found = resolve(values)
		self.assertEqual(found["dd_allocated_name"], "Administrator")
		self.assertNotIn("dd_secret", found)

	def test_the_form_asks_for_a_new_record_too(self):
		from commons.derived_docfields.api import resolve

		frappe.set_user(self.reader)
		found = resolve({"doctype": HOST, "__islocal": 1, "allocated_to": "Administrator"})
		self.assertEqual(found["dd_allocated_name"], "Administrator")

	def test_asking_needs_write_permission(self):
		from commons.derived_docfields.api import resolve

		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			resolve({"doctype": HOST, "name": self.mine, "allocated_to": "Administrator"})

	def link_as(self, **properties):
		"""ToDo.allocated_to with `properties`, for as long as the `with` lasts, in this process's meta."""
		from contextlib import ExitStack

		df = frappe.get_meta(HOST).get_field("allocated_to")
		stack = ExitStack()
		for prop, value in properties.items():
			stack.enter_context(patch.object(df, prop, value))
		return stack

	def ask(self, **values):
		from commons.derived_docfields.api import resolve

		return resolve({"doctype": HOST, **values}).get("dd_allocated_name")

	def test_asking_keeps_a_link_above_the_askers_permlevel(self):
		"""Allowed to save the ToDo is not allowed to repoint a link at a permlevel they can't write."""
		frappe.set_user(self.reader)
		with self.link_as(permlevel=1):
			self.assertEqual(self.ask(name=self.mine, allocated_to="Administrator"), READER_NAME)
			# A new record starts from the default, as saving it would.
			self.assertIsNone(self.ask(__islocal=1, allocated_to="Administrator"))
		frappe.set_user("Administrator")
		with self.link_as(permlevel=1):
			self.assertEqual(self.ask(name=self.mine, allocated_to="Administrator"), "Administrator")

	def test_asking_keeps_a_read_only_link(self):
		frappe.set_user(self.reader)
		with self.link_as(read_only=1):
			self.assertEqual(self.ask(name=self.mine, allocated_to="Administrator"), READER_NAME)

	def test_asking_keeps_a_link_set_only_once_but_not_before_it_is_set(self):
		frappe.set_user(self.reader)
		with self.link_as(set_only_once=1):
			self.assertEqual(self.ask(name=self.mine, allocated_to="Administrator"), READER_NAME)
			self.assertEqual(self.ask(__islocal=1, allocated_to="Administrator"), "Administrator")

	def test_asking_keeps_the_links_of_a_submitted_record(self):
		"""Judged by the stored docstatus: the form could claim 0."""
		frappe.db.set_value(HOST, self.mine, "docstatus", 1, update_modified=False)
		frappe.set_user(self.reader)
		values = dict(name=self.mine, allocated_to="Administrator", docstatus=0)
		self.assertEqual(self.ask(**values), READER_NAME)
		with self.link_as(allow_on_submit=1):
			self.assertEqual(self.ask(**values), "Administrator")

	def test_asking_keeps_the_type_of_a_dynamic_link_too(self):
		"""Repointing `reference_type` alone would read another doctype's record of the same name."""
		frappe.set_user(self.reader)
		df = frappe.get_meta(HOST).get_field("reference_type")
		from commons.derived_docfields.api import resolve

		with patch.object(df, "permlevel", 1):
			found = resolve(
				{
					"doctype": HOST,
					"name": self.theirs,
					"reference_type": "Role",
					"reference_name": self.reader,
				}
			)
		self.assertEqual(found["dd_reference_created"], frappe.db.get_value("User", self.reader, "creation"))

	# Defining
	# --------

	def test_a_derived_field_is_virtual_and_read_only(self):
		doc = frappe.get_doc("Custom Field", {"dt": HOST, "fieldname": "dd_allocated_name"})
		self.assertEqual((doc.is_virtual, doc.read_only), (1, 1))

	def test_a_derived_link_ignores_user_permissions(self):
		"""Core builds User Permission conditions from every Link, as columns."""
		doc = frappe.get_doc("Custom Field", {"dt": HOST, "fieldname": "dd_allocated_language"})
		self.assertEqual(doc.ignore_user_permissions, 1)

	def test_a_derived_link_takes_its_options_from_the_source(self):
		doc = define("dd_language_again", "Link", "allocated_to.language")
		self.assertEqual(doc.options, "Language")

	def assertRefused(self, *args, exc=frappe.ValidationError, **kwargs):
		with self.assertRaises(exc):
			define(*args, **kwargs)

	def test_refuses_a_malformed_path(self):
		self.assertRefused("dd_bad", "Data", "allocated_to")
		self.assertRefused("dd_bad", "Data", "allocated_to.full_name.more")

	def test_refuses_a_link_that_is_not_there(self):
		self.assertRefused("dd_bad", "Data", "no_such_link.full_name")

	def test_refuses_following_something_that_is_not_a_link(self):
		self.assertRefused("dd_bad", "Data", "description.full_name")

	def test_refuses_a_target_with_no_column(self):
		self.assertRefused("dd_bad", "Data", "allocated_to.no_such_field")
		self.assertRefused("dd_bad", "Data", "allocated_to.roles")

	def test_refuses_a_loop(self):
		define("dd_loop_a", "Link", "allocated_to.name", options="User")
		define("dd_loop_b", "Link", "dd_loop_a.name", options="User")
		doc = frappe.get_doc("Custom Field", {"dt": HOST, "fieldname": "dd_loop_a"})
		doc.derived_from = "dd_loop_b.name"
		with self.assertRaises(frappe.ValidationError):
			doc.save()

	def test_refuses_a_dynamic_link_without_candidates(self):
		self.assertRefused("dd_bad", "Datetime", "reference_name.creation")

	def test_refuses_candidates_on_a_plain_link(self):
		self.assertRefused("dd_bad", "Data", "allocated_to.full_name", derived_from_doctypes="User")

	def test_refuses_a_candidate_without_the_target_field(self):
		self.assertRefused("dd_bad", "Data", "reference_name.full_name", derived_from_doctypes="User\nRole")

	def test_refuses_a_fieldtype_that_cannot_hold_the_value(self):
		self.assertRefused("dd_bad", "Int", "allocated_to.full_name")
		self.assertRefused("dd_bad", "Link", "allocated_to.language", options="Currency")

	def test_refuses_a_derived_dynamic_link(self):
		self.assertRefused("dd_bad", "Dynamic Link", "allocated_to.full_name", options="reference_type")

	def test_refuses_new_definitions_while_switched_off(self):
		switch(on=False)
		self.assertRefused("dd_bad", "Data", "allocated_to.full_name")

	def test_a_definer_must_be_able_to_read_the_path(self):
		node = registry.plan(HOST, "dd_reference_created")
		frappe.set_user(self.reader)
		with self.assertRaises(frappe.PermissionError):
			validation.check_readable(node)

	def test_relabelling_while_switched_off_is_allowed(self):
		switch(on=False)
		doc = frappe.get_doc("Custom Field", {"dt": HOST, "fieldname": "dd_allocated_name"})
		doc.label = "Allocated To (Name)"
		frappe.flags.in_create_custom_fields = True
		try:
			doc.save()
		finally:
			frappe.flags.in_create_custom_fields = False

	def test_refuses_clearing_derived_from(self):
		"""What's left would be virtual but not derived, and core would eval its `options` on every load."""
		doc = frappe.get_doc("Custom Field", {"dt": HOST, "fieldname": "dd_allocated_language"})
		doc.derived_from = ""
		# The flag keeps a save that wrongly got through from altering the table,
		# which would commit this test's records.
		frappe.flags.in_create_custom_fields = True
		try:
			with self.assertRaises(frappe.ValidationError):
				doc.save()
		finally:
			frappe.flags.in_create_custom_fields = False
		self.assertIn("dd_allocated_language", registry.definitions()[HOST])

	def test_an_ordinary_custom_field_is_left_alone(self):
		doc = frappe.get_doc(
			{
				"doctype": "Custom Field",
				"dt": HOST,
				"fieldname": "dd_plain",
				"label": "Dd Plain",
				"fieldtype": "Data",
				"derived_from": " ",
				"insert_after": "description",
			}
		)
		frappe.flags.in_create_custom_fields = True
		try:
			doc.insert()
			doc.label = "Plain, relabelled"
			doc.save()
		finally:
			frappe.flags.in_create_custom_fields = False
			frappe.clear_cache(doctype=HOST)
		self.assertEqual((doc.derived_from, doc.is_virtual, doc.read_only), (None, 0, 0))

	def test_deleting_a_field_forgets_it(self):
		"""Core runs `on_trash` before the row goes; anything reading in between must not keep it."""
		doc = define("dd_short_lived", "Data", "allocated_to.full_name")
		self.assertIn("dd_short_lived", registry.definitions()[HOST])
		frappe.delete_doc("Custom Field", doc.name)
		self.assertNotIn("dd_short_lived", registry.definitions()[HOST])

	def test_a_controller_imported_before_the_save_commits_is_dropped_once_it_has(self):
		"""Core drops the controller before commit; a worker importing in between kept it for good.

		Without the new field's descriptor, core evaluates a derived Link's
		`options` as Python, and every form of the doctype fails on that worker.
		"""
		from frappe.model.base_document import get_controller

		from commons.derived_docfields.document import DerivedValue

		stale = get_controller(HOST)
		already = len(frappe.db.after_commit._functions)
		define("dd_late_language", "Link", "allocated_to.language", options="Language")
		queued = list(frappe.db.after_commit._functions)[already:]
		# What another worker would hold, having read the definitions before the commit.
		frappe.controllers.setdefault(frappe.local.site, {})[HOST] = stale
		self.assertNotIsInstance(getattr(get_controller(HOST), "dd_late_language", None), DerivedValue)

		for callback in queued:
			callback()
		self.assertIsInstance(getattr(get_controller(HOST), "dd_late_language", None), DerivedValue)

	def test_check_all_reports_broken_fields(self):
		broken = registry.Definition(HOST, "dd_allocated_name", "allocated_to", "no_such_field", (), False)
		with (
			patch.object(registry, "definitions", return_value={HOST: {"dd_allocated_name": broken}}),
			patch.object(frappe, "log_error") as log_error,
		):
			validation.check_all()
		self.assertEqual(log_error.call_count, 1)


class TestAliases(unittest.TestCase):
	"""Site-less: what joins are called."""

	def test_readable_where_it_fits(self):
		self.assertEqual(alias(("instructor", "member")), "dd_instructor__member")
		self.assertEqual(alias(("reference_name", "Sales Invoice")), "dd_reference_name__sales_invoice")

	def test_hashed_where_it_does_not(self):
		long = alias(tuple("a_rather_long_link_fieldname" for _ in range(4)))
		self.assertLessEqual(len(long), 64)
		self.assertNotEqual(long, alias(tuple("a_rather_long_link_fieldname" for _ in range(5))))


class TestDefinitions(unittest.TestCase):
	"""Site-less: reading what a Custom Field declares."""

	def test_parse(self):
		definition = registry.parse("ToDo", "x", " allocated_to.full_name ", "User\n\nRole\nUser", 1)
		self.assertEqual(
			(definition.link_field, definition.target_field, definition.candidates, definition.in_wildcard),
			("allocated_to", "full_name", ("User", "Role"), True),
		)

	def test_parse_refuses_anything_but_two_names(self):
		for bad in ("", "allocated_to", "a.b.c", "a b.c", ".c", "a."):
			self.assertIsNone(registry.parse("ToDo", "x", bad))


def run():
	"""Run this suite against a site by hand, verbosely."""
	original_user = frappe.session.user
	try:
		result = unittest.TextTestRunner(verbosity=2).run(
			unittest.TestSuite(
				unittest.defaultTestLoader.loadTestsFromTestCase(case)
				for case in (TestDerivedDocfields, TestAliases, TestDefinitions)
			)
		)
		if not result.wasSuccessful():
			raise RuntimeError("Derived docfields tests failed")
		return dict(tests=result.testsRun, success=True)
	finally:
		frappe.db.rollback()
		forget()
		frappe.set_user(original_user)
