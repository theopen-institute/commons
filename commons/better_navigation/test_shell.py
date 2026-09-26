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

from commons.api_integrations.claude import client as claude
from commons.shell import workspaces
from commons.shell.doctype.commons_workspace import commons_workspace as controller
from commons.shell.doctype.commons_workspace.commons_workspace import CommonsWorkspace

# `frappe._` reaches for the translation cache and, failing that, for a log file
# neither of which a site-less run has. See `self_service.test_self_service_api`.
_logger = patch("frappe.logger", return_value=logging.getLogger(__name__))


def setUpModule():
	_logger.start()


def tearDownModule():
	_logger.stop()


# What a site runs, unless a test says otherwise: everything this app can use.
ALL_APPS = ("frappe", "erpnext", "hrms", "commons")


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


def with_documents(test, parents, items, installed=True, absent=(), apps=ALL_APPS, claude_key=False):
	"""Stand in for the database with a fixed set of workspaces and their rows.

	Three separate facts about the site, because resolving a row now asks three
	separate questions and a stand-in that conflated them would pass while the
	real thing failed.

	`installed` is whether `Commons Workspace` itself is here -- the deploy
	window `workspaces.installed` exists for. `absent` names other doctypes this
	site does not have, such as `Leave Application` on a site running no HRMS.
	`apps` is the site's installed apps, which is what procurement is missing
	without ERPNext: its own doctype is this app's and is never absent. See
	`shell.pages.available`, and `commons.commons_core.apps` on why the two are asked
	differently.

	`claude_key` is whether `Claude Settings` holds a key, which is a fourth
	fact and not a doctype: document capture needs ERPNext and a key both. Off
	by default, as it is on a fresh site.
	"""
	absent = set(absent)
	test.enterContext(patch.object(claude, "available", return_value=claude_key))

	# The doctype existence checks in front of the queries. Patched as a whole
	# `frappe.db`, because site-less there is no connection for the proxy to
	# hand an attribute back from.
	def exists(doctype, name=None, *args, **kwargs):
		if doctype == "DocType":
			if name == workspaces.WORKSPACE:
				return installed
			return name not in absent
		return installed

	test.enterContext(patch.object(workspaces.frappe, "db", SimpleNamespace(exists=exists)))
	test.enterContext(patch.object(workspaces.frappe, "get_installed_apps", return_value=list(apps)))

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
				("page", "statement", "Profile"),
				("page", "leave", "Requests"),
				("page", "expense", "Requests"),
				("page", "procurement", "Requests"),
				("page", "attendance", "Teaching"),
				("page", "reconciliation", "Accounts"),
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
		self.assertEqual(
			[row["key"] for row in rows],
			["announcements", "statement", "leave", "expense", "procurement", "attendance", "reconciliation"],
		)


class TestPagesWhoseAppIsNotInstalled(TestCase):
	"""Leave and expenses on a site that does not run HRMS.

	HRMS is not in `required_apps` -- see `hooks.py` -- so `Leave Application`
	and `Expense Claim` may simply not be doctypes here. A workspace row naming
	one is then a saved row that no longer resolves, the same case as a record
	type somebody deleted, and it is dropped the same way: the sidebar has to
	agree with the endpoints behind the pages, which refuse
	(`approvals.RequestType.available`), and with the desk's Awesome Bar, which
	reads these same rows.

	The `Commons Workspace Item` Select goes on offering every page whatever a
	site has installed, which is why this is settled when the rows are read
	rather than when they are saved.
	"""

	ABSENT = ("Leave Application", "Expense Claim")

	def setUp(self):
		with_policies(self, policy("Employee", "Profile", "employee"))

	def test_the_default_workspace_keeps_only_the_sections_that_are_here(self):
		with_documents(self, [], [], absent=self.ABSENT)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual(
			[row["key"] for row in rows],
			["announcements", "Employee", "statement", "procurement", "attendance", "reconciliation"],
		)

	def test_a_configured_row_naming_one_is_dropped(self):
		with_documents(
			self,
			[parent("Staff")],
			[
				item("Staff", page="Announcements", idx=1),
				item("Staff", page="Leave Request", group="Requests", idx=2),
				item("Staff", page="Procurement", group="Requests", idx=3),
			],
			absent=self.ABSENT,
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["announcements", "procurement"])

	def test_a_workspace_left_holding_nothing_else_falls_back_to_the_default(self):
		"""A workspace with no rows is dropped, and with it the last one is.

		The switcher would otherwise offer somewhere empty and the landing
		redirect would have nowhere to land -- so `workspaces()` answers with the
		default, exactly as it does for a site that has configured none.
		"""
		with_documents(
			self,
			[parent("Time Off")],
			[item("Time Off", page="Leave Request", idx=1)],
			absent=self.ABSENT,
		)
		found = workspaces.workspaces()
		self.assertEqual(len(found), 1)
		self.assertIsNone(found[0]["name"])

	def test_a_site_that_has_hrms_keeps_both(self):
		"""The same rows, on the site the assertions above are the contrast to."""
		with_documents(self, [], [])
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual(
			[row["key"] for row in rows],
			[
				"announcements",
				"Employee",
				"statement",
				"leave",
				"expense",
				"procurement",
				"attendance",
				"reconciliation",
			],
		)

	def test_procurement_goes_with_erpnext_rather_than_with_a_doctype(self):
		"""`Procurement Request` is this app's own, so the doctype is still here.

		Which is exactly why the row cannot be decided by the doctype: without
		ERPNext there is no Company to spend against, no Item to order and no
		Material Request to hand over to, and a row offering that page would open
		one that cannot load. The section names the app instead --
		`Procurement.requires_apps` -- and this is the navigation agreeing.
		"""
		# `GL Entry` goes with ERPNext, so a site without it has no ledger either
		# -- named here rather than inferred from `apps`, because the stand-in
		# answers the two questions separately and so does the code under test.
		# `Bank Transaction` goes with it for the same reason.
		with_documents(
			self, [], [], absent=("GL Entry", "Bank Transaction"), apps=("frappe", "hrms", "commons")
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual(
			[row["key"] for row in rows], ["announcements", "Employee", "leave", "expense", "attendance"]
		)

	def test_a_site_with_neither_keeps_the_pages_that_need_neither(self):
		"""Bare Frappe: announcements and whatever self-service is configured."""
		with_documents(
			self, [], [], absent=(*self.ABSENT, "GL Entry", "Bank Transaction"), apps=("frappe", "commons")
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["announcements", "Employee", "attendance"])


class TestTheStatementPage(TestCase):
	"""The one shipped page that is not a request section.

	It is here for the same reason leave is: it can be absent. `Account Balance`
	reads the general ledger, so a site with no ERPNext has no such page -- and
	that answer comes from `pages.PAGE_AVAILABILITY` rather than from a
	`RequestType`, which is a second code path through `pages.available` and so a
	second thing that can quietly stop being asked.
	"""

	def setUp(self):
		with_policies(self, policy("Employee", "Profile", "employee"))

	def test_is_offered_where_there_is_a_ledger(self):
		with_documents(self, [], [])
		rows = workspaces.workspaces()[0]["items"]
		row = next(row for row in rows if row["key"] == "statement")
		# Under Profile, and unnamed: like every shipped page, what it is called
		# and what it is drawn with live in the frontend.
		self.assertEqual(row["group"], "Profile")
		self.assertIsNone(row["label"])
		self.assertIsNone(row["icon"])

	def test_is_absent_where_there_is_not(self):
		with_documents(self, [], [], absent=("GL Entry",))
		rows = workspaces.workspaces()[0]["items"]
		self.assertNotIn("statement", [row["key"] for row in rows])

	def test_a_configured_row_naming_it_is_dropped_too(self):
		"""The same rule as leave's, and it has to be: the Select offers the page
		on every site, so a workspace saved on one that has a ledger has to stop
		resolving on one that does not."""
		with_documents(
			self,
			[parent("Staff")],
			[
				item("Staff", page="Announcements", idx=1),
				item("Staff", page="Account Balance", idx=2),
			],
			absent=("GL Entry",),
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["announcements"])


class TestTheAttendanceRegisterRow(TestCase):
	"""The register, which can be absent for a third reason again.

	Not a `RequestType` and not `PAGE_AVAILABILITY`'s only entry any more, so it
	is worth its own class for the same reason the statement has one: the answer
	comes from a different place, and a different place is a different thing to
	stop being asked.

	It is deliberately *not* tested here that a student does not get the row.
	That is `pages.PAGE_ACCESS`, which is a permission question about a person
	rather than a fact about the site, and the default workspace does not ask it
	-- the frontend and the Awesome Bar each do. See `commons.shell.search`.
	"""

	ABSENT = ("Course Schedule", "Student Attendance")

	def setUp(self):
		with_policies(self, policy("Employee", "Profile", "employee"))

	def test_is_offered_where_the_site_teaches(self):
		with_documents(self, [], [])
		rows = workspaces.workspaces()[0]["items"]
		row = next(row for row in rows if row["key"] == "attendance")
		# After the requests, under its own heading, and unnamed like every
		# shipped page.
		self.assertEqual(row["group"], "Teaching")
		self.assertIsNone(row["label"])
		self.assertIsNone(row["icon"])
		keys = [row["key"] for row in rows]
		self.assertEqual(keys.index("attendance"), keys.index("procurement") + 1)

	def test_is_absent_where_it_does_not(self):
		with_documents(self, [], [], absent=self.ABSENT)
		rows = workspaces.workspaces()[0]["items"]
		self.assertNotIn("attendance", [row["key"] for row in rows])

	def test_half_an_education_module_is_not_enough(self):
		"""Either doctype missing takes the row away.

		They arrive together in practice. The register is made of both -- a
		session and a mark against it -- and a sidebar that offered it on one of
		them would be offering a page whose first call fails.
		"""
		with_documents(self, [], [], absent=("Student Attendance",))
		rows = workspaces.workspaces()[0]["items"]
		self.assertNotIn("attendance", [row["key"] for row in rows])

	def test_a_configured_row_naming_it_is_dropped_too(self):
		with_documents(
			self,
			[parent("Staff")],
			[
				item("Staff", page="Announcements", idx=1),
				item("Staff", page="Attendance", idx=2),
			],
			absent=self.ABSENT,
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["announcements"])


class TestTheReconciliationRow(TestCase):
	"""Bank reconciliation, absent on a site that keeps no bank statements.

	As with the register, whether a *reader* gets the row is `PAGE_ACCESS`
	and is not asked by the default workspace.
	"""

	def setUp(self):
		with_policies(self, policy("Employee", "Profile", "employee"))

	def test_is_offered_last_under_accounts(self):
		with_documents(self, [], [])
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual(rows[-1]["key"], "reconciliation")
		self.assertEqual(rows[-1]["group"], "Accounts")
		self.assertIsNone(rows[-1]["label"])

	def test_is_absent_without_bank_transactions(self):
		with_documents(self, [], [], absent=("Bank Transaction",))
		rows = workspaces.workspaces()[0]["items"]
		self.assertNotIn("reconciliation", [row["key"] for row in rows])

	def test_is_absent_without_bank_accounts(self):
		with_documents(self, [], [], absent=("Bank Account",))
		rows = workspaces.workspaces()[0]["items"]
		self.assertNotIn("reconciliation", [row["key"] for row in rows])

	def test_a_configured_row_names_it_by_its_desk_wording(self):
		with_documents(
			self,
			[parent("Finance")],
			[item("Finance", page="Bank Reconciliation", idx=1)],
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["reconciliation"])


class TestTheCaptureRow(TestCase):
	"""Document capture, after reconciliation under Accounts, on a site that
	can read scans. Whether a *reader* gets it is `PAGE_ACCESS` again."""

	def setUp(self):
		with_policies(self, policy("Employee", "Profile", "employee"))

	def test_is_offered_last_under_accounts_once_there_is_a_key(self):
		with_documents(self, [], [], claude_key=True)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows[-2:]], ["reconciliation", "capture"])
		self.assertEqual(rows[-1]["group"], "Accounts")
		self.assertIsNone(rows[-1]["label"])

	def test_is_absent_without_a_key(self):
		with_documents(self, [], [])
		rows = workspaces.workspaces()[0]["items"]
		self.assertNotIn("capture", [row["key"] for row in rows])

	def test_is_absent_without_erpnext(self):
		with_documents(self, [], [], absent=("Purchase Invoice",), claude_key=True)
		rows = workspaces.workspaces()[0]["items"]
		self.assertNotIn("capture", [row["key"] for row in rows])

	def test_a_configured_row_names_it_by_its_desk_wording(self):
		with_documents(
			self,
			[parent("Finance")],
			[item("Finance", page="Document Capture", idx=1)],
			claude_key=True,
		)
		rows = workspaces.workspaces()[0]["items"]
		self.assertEqual([row["key"] for row in rows], ["capture"])


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
