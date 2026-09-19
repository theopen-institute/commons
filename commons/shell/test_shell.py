"""What the sidebar resolves to, and what a workspace refuses to be saved as.

Two things are worth pinning here, and they are the two that would fail
silently.

*The default.* A site that has configured no workspace keeps the sidebar this
app used to hard-code -- the ungated page, then everything self-service under
Profile, then the three request sections under Requests. Nobody would notice
that drifting until an install somewhere came up with a sidebar in a different
order, so it is asserted row by row.

*The one-workspace rule.* A page sits in exactly one workspace, because that is
what lets the header say which workspace you are in. It is enforced across
documents, which is the kind of check that quietly stops working.

Site-less, like `self_service.test_self_service_api`: `frappe.get_all` is what
stands between this module and a database, so it is what the tests stand in
for.
"""

import logging
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.shell import api, workspaces
from commons.shell.doctype.commons_workspace import commons_workspace as controller
from commons.shell.doctype.commons_workspace.commons_workspace import CommonsWorkspace

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. See `self_service.test_self_service_api`.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


def policy(doctype, label, slug, icon=None, nav_order=0):
	return {
		"doctype": doctype,
		"label": label,
		"slug": slug,
		"icon": icon,
		"nav_order": nav_order,
	}


def with_policies(test, *policies):
	"""Stand in for the self-service registry with a fixed set of record types."""
	resolved = {row["doctype"]: row for row in policies}
	test.enterContext(patch.object(workspaces.registry, "policies", return_value=resolved))
	test.enterContext(
		patch.object(
			workspaces.registry,
			"registered",
			return_value=sorted(resolved, key=lambda key: (resolved[key]["nav_order"], key)),
		)
	)
	test.enterContext(patch.object(workspaces.registry, "policy", side_effect=lambda key: resolved[key]))


def with_documents(test, parents, items, installed=True):
	"""Stand in for the database with a fixed set of workspaces and their rows."""
	# The doctype existence check in front of both queries. Patched as a whole
	# `frappe.db`, because site-less there is no connection for the proxy to
	# hand an attribute back from.
	test.enterContext(
		patch.object(workspaces.frappe, "db", SimpleNamespace(exists=lambda *args, **kwargs: installed))
	)

	def get_all(doctype, **kwargs):
		rows = parents if doctype == workspaces.WORKSPACE else items
		if doctype == workspaces.WORKSPACE:
			rows = [row for row in rows if row.get("enabled")]
		else:
			wanted = kwargs.get("filters", {}).get("parent")
			if wanted and wanted[0] == "in":
				rows = [row for row in rows if row["parent"] in wanted[1]]
			elif wanted:
				rows = [row for row in rows if row["parent"] == wanted]
			# The query orders by parent then idx, and the order is the sidebar.
			rows = sorted(rows, key=lambda row: (row["parent"], row["idx"]))
		return [frappe._dict(row) for row in rows]

	test.enterContext(patch.object(workspaces.frappe, "get_all", side_effect=get_all))


def parent(name, title=None, enabled=1, icon=None, logo=None, nav_order=0):
	return {
		"name": name,
		"title": title or name,
		"enabled": enabled,
		"icon": icon,
		"logo": logo,
		"nav_order": nav_order,
	}


def item(parent_name, page=None, record=None, group=None, label=None, icon=None, idx=1):
	return {
		"parent": parent_name,
		"item_type": "Page" if page else "Self Service Record",
		"page": page,
		"self_service_record": record,
		"item_group": group,
		"label": label,
		"icon": icon,
		"idx": idx,
	}


class TestDefaultWorkspace(TestCase):
	"""The sidebar a site gets before it has configured one."""

	def setUp(self):
		with_policies(
			self,
			policy("Employee", "Profile", "employee", icon="lucide-id-card"),
			policy("Bank Account", "Bank Accounts", "bank-accounts", nav_order=1),
		)
		with_documents(self, [], [])

	def test_is_the_only_workspace(self):
		found = workspaces.workspaces()
		self.assertEqual(len(found), 1)
		self.assertEqual(found[0]["title"], "Staff Member")
		# Null rather than a name: there is no document behind it.
		self.assertIsNone(found[0]["name"])

	def test_holds_the_sidebar_this_app_shipped(self):
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual(
			[(row["kind"], row["key"], row["group"]) for row in rows],
			[
				("page", "announcements", None),
				("record", "Employee", "Profile"),
				("record", "Bank Account", "Profile"),
				("page", "leave", "Requests"),
				("page", "expense", "Requests"),
				("page", "procurement", "Requests"),
			],
		)

	def test_record_rows_say_what_their_record_says(self):
		rows = workspaces.workspaces()[0]["items"]
		employee = next(row for row in rows if row["key"] == "Employee")
		self.assertEqual(employee["label"], "Profile")
		self.assertEqual(employee["icon"], "lucide-id-card")
		self.assertEqual(employee["slug"], "employee")

	def test_shipped_pages_are_left_unnamed(self):
		"""The label and the icon of a page this app ships live in the frontend."""
		rows = workspaces.workspaces()[0]["items"]
		leave = next(row for row in rows if row["key"] == "leave")
		self.assertIsNone(leave["label"])
		self.assertIsNone(leave["icon"])

	def test_survives_a_site_with_no_self_service(self):
		with patch.object(workspaces.registry, "registered", return_value=[]):
			rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["announcements", "leave", "expense", "procurement"])


class TestConfiguredWorkspaces(TestCase):
	"""What the documents resolve to once a site has written some."""

	def setUp(self):
		with_policies(self, policy("Employee", "Profile", "employee", icon="lucide-id-card"))

	def test_rows_keep_the_order_of_the_table(self):
		with_documents(
			self,
			[parent("Staff")],
			[
				item("Staff", page="Leave Request", group="Requests", idx=2),
				item("Staff", page="Announcements", idx=1),
			],
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["announcements", "leave"])

	def test_an_override_wins_over_what_a_row_would_be_called(self):
		with_documents(
			self,
			[parent("Staff")],
			[
				item("Staff", page="Leave Request", label="Time off", icon="lucide-plane"),
				item("Staff", record="Employee", label="Me", icon="lucide-user"),
			],
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual(
			[(row["label"], row["icon"]) for row in rows],
			[("Time off", "lucide-plane"), ("Me", "lucide-user")],
		)

	def test_a_record_type_that_is_no_longer_self_service_drops_out(self):
		with_documents(
			self,
			[parent("Staff")],
			[
				item("Staff", page="Announcements", idx=1),
				item("Staff", record="Bank Account", idx=2),
			],
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["announcements"])

	def test_a_workspace_left_with_nothing_is_not_offered(self):
		with_documents(
			self,
			[parent("Staff"), parent("Money", nav_order=1)],
			[item("Staff", page="Announcements"), item("Money", record="Bank Account")],
		)
		self.assertEqual([row["title"] for row in workspaces.workspaces()], ["Staff"])

	def test_a_site_whose_workspaces_all_resolve_to_nothing_gets_the_default(self):
		with_documents(self, [parent("Money")], [item("Money", record="Bank Account")])
		self.assertEqual(workspaces.workspaces()[0]["title"], workspaces.DEFAULT_TITLE)

	def test_marks_are_the_workspace_s_own_or_nobody_s(self):
		with_documents(
			self,
			[parent("Staff", icon="lucide-users", logo="/files/mark.svg"), parent("Money", nav_order=1)],
			[item("Staff", page="Announcements"), item("Money", page="Leave Request")],
		)
		found = {row["title"]: row for row in workspaces.workspaces()}
		self.assertEqual((found["Staff"]["icon"], found["Staff"]["logo"]), ("lucide-users", "/files/mark.svg"))
		# Null, not a guess: the frontend holds what this app's own mark is.
		self.assertEqual((found["Money"]["icon"], found["Money"]["logo"]), (None, None))


class TestClaims(TestCase):
	"""Which rows another workspace has already taken."""

	def test_counts_every_other_enabled_workspace(self):
		with_documents(
			self,
			[parent("Staff"), parent("Money", nav_order=1)],
			[item("Staff", page="Announcements"), item("Money", record="Employee")],
		)
		self.assertEqual(
			workspaces.claimed_elsewhere("Staff"),
			{("Self Service Record", "Employee"): "Money"},
		)

	def test_a_workspace_does_not_claim_against_itself(self):
		with_documents(self, [parent("Staff")], [item("Staff", page="Announcements")])
		self.assertEqual(workspaces.claimed_elsewhere("Staff"), {})

	def test_a_disabled_workspace_claims_nothing(self):
		with_documents(
			self,
			[parent("Staff"), parent("Money", enabled=0, nav_order=1)],
			[item("Staff", page="Announcements"), item("Money", page="Leave Request")],
		)
		self.assertEqual(workspaces.claimed_elsewhere("Staff"), {})


def workspace(name="Staff", enabled=1, icon=None, rows=()):
	"""A `Commons Workspace` far enough built to validate, and no further."""
	doc = CommonsWorkspace.__new__(CommonsWorkspace)
	doc.name = name
	doc.enabled = enabled
	doc.icon = icon
	doc.items = [frappe._dict(row) for row in rows]
	return doc


def row(idx, page=None, record=None, icon=None):
	return {
		"idx": idx,
		"item_type": "Page" if page or not record else "Self Service Record",
		"page": page,
		"self_service_record": record,
		"icon": icon,
	}


class TestWorkspaceRows(TestCase):
	"""What a workspace refuses to be saved as."""

	def setUp(self):
		self.throw = self.enterContext(patch.object(controller.frappe, "throw", side_effect=ValueError))
		with_documents(self, [], [])

	def test_a_row_may_name_a_page_and_a_record_type(self):
		workspace(rows=[row(1, page="Announcements"), row(2, record="Employee")]).validate_rows()
		self.assertFalse(self.throw.called)

	def test_a_page_this_app_does_not_have_is_refused(self):
		with self.assertRaises(ValueError):
			workspace(rows=[row(1, page="Ledger")]).validate_rows()

	def test_a_row_naming_nothing_is_refused(self):
		with self.assertRaises(ValueError):
			workspace(rows=[row(1)]).validate_rows()

	def test_the_same_page_twice_in_one_workspace_is_refused(self):
		with self.assertRaises(ValueError):
			workspace(rows=[row(1, page="Announcements"), row(2, page="Announcements")]).validate_rows()

	def test_a_page_another_workspace_holds_is_refused(self):
		with_documents(
			self,
			[parent("Staff"), parent("Money", nav_order=1)],
			[item("Money", page="Announcements")],
		)
		with self.assertRaises(ValueError):
			workspace(rows=[row(1, page="Announcements")]).validate_rows()

	def test_a_disabled_workspace_may_hold_what_an_enabled_one_does(self):
		"""Nobody is offered it, so it is taking nothing from anybody."""
		with_documents(self, [parent("Money")], [item("Money", page="Announcements")])
		workspace(enabled=0, rows=[row(1, page="Announcements")]).validate_rows()
		self.assertFalse(self.throw.called)

	def test_an_icon_the_sidebar_cannot_draw_is_refused(self):
		with self.assertRaises(ValueError):
			workspace(rows=[row(1, page="Announcements", icon="lucide-rocket")]).validate_rows()

	def test_an_icon_from_the_palette_is_kept(self):
		workspace(icon="lucide-inbox", rows=[row(1, page="Announcements", icon="lucide-plane")]).validate_rows()
		self.assertFalse(self.throw.called)


class TestTitle(TestCase):
	"""What the app calls itself, and what answers when nobody has said."""

	def title(self, stored, installed=True):
		# The whole of `frappe.db`, not two of its methods: site-less there is no
		# connection for the proxy to hand an attribute back from.
		database = SimpleNamespace(
			exists=lambda *args, **kwargs: installed,
			get_single_value=lambda *args, **kwargs: stored,
		)
		with patch.object(api.frappe, "db", database):
			return api.title()

	def test_the_site_s_own_name_wins(self):
		self.assertEqual(self.title("  Staff Portal  "), "Staff Portal")

	def test_a_blank_setting_reads_as_unset(self):
		self.assertEqual(self.title("   "), api.DEFAULT_TITLE)

	def test_a_single_that_has_never_been_saved_reads_as_unset(self):
		self.assertEqual(self.title(None), api.DEFAULT_TITLE)

	def test_a_site_migrating_into_this_app_has_no_doctype_yet(self):
		self.assertEqual(self.title("Staff Portal", installed=False), api.DEFAULT_TITLE)


class TestBeforeMigrate(TestCase):
	"""The deploy window: this app's code is on the site, its doctypes are not."""

	def setUp(self):
		with_policies(self, policy("Employee", "Profile", "employee"))
		with_documents(self, [parent("Staff")], [item("Staff", page="Announcements")], installed=False)

	def test_the_sidebar_is_the_default_rather_than_a_failure(self):
		found = workspaces.workspaces()
		self.assertEqual([row["title"] for row in found], [workspaces.DEFAULT_TITLE])

	def test_nothing_is_claimed_by_a_workspace_that_cannot_exist(self):
		self.assertEqual(workspaces.claimed_elsewhere(None), {})
