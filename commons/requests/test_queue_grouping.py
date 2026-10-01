"""How an approval queue is grouped, and what the figure over a group means.

The grouping used to be the page's. The total printed beside each group is
money, so it is arrived at once, on the server; these pin what a group's
`estimate` is allowed to claim.

What a queue is grouped *by* is the site's (`procurement_group_by` in Commons
Settings): department where it never said, nothing where it cleared it or named
a field the doctype does not have. The approver picker is pinned here too,
since it is the other place this section used to carry one organisation's idea
of who decides a request.
"""

import inspect
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch

import frappe

from commons.requests import procurement as api
from commons.requests.procurement import group_requests

# The body, without `validate_and_sanitize_search_inputs`, which reaches the
# database before it runs and so cannot be called site-less.
get_procurement_approvers = inspect.unwrap(api.get_procurement_approvers)

DEPARTMENT = SimpleNamespace(
	fieldname="department", fieldtype="Link", options="Department", label="Department"
)


def request(name, department, currency="GBP", cost=0):
	return frappe._dict(name=name, department=department, currency=currency, total_estimated_cost=cost)


class TestGroupRequests(TestCase):
	def setUp(self):
		# Department shows no titles in links, so a value is its own label.
		titles = patch.object(api, "_link_titles", return_value={})
		titles.start()
		self.addCleanup(titles.stop)

	def test_one_value_is_one_group(self):
		groups = group_requests(
			[request("A", "Estates", cost=100), request("B", "Estates", cost=50)], DEPARTMENT
		)
		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["requests"], ["A", "B"])
		self.assertEqual(groups[0]["estimate"], 150)
		self.assertEqual((groups[0]["value"], groups[0]["label"]), ("Estates", "Estates"))

	def test_a_mixture_of_currencies_has_no_honest_total(self):
		groups = group_requests(
			[
				request("A", "Estates", currency="GBP", cost=100),
				request("B", "Estates", currency="EUR", cost=50),
			],
			DEPARTMENT,
		)
		self.assertIsNone(groups[0]["estimate"])

	def test_groups_are_ordered_by_label_so_acting_does_not_reshuffle_them(self):
		groups = group_requests([request("A", "Works"), request("B", "Estates")], DEPARTMENT)
		self.assertEqual([group["value"] for group in groups], ["Estates", "Works"])

	def test_a_request_without_a_value_sorts_last(self):
		groups = group_requests([request("A", None), request("B", "Estates")], DEPARTMENT)
		self.assertEqual([group["value"] for group in groups], ["Estates", None])
		self.assertEqual((groups[1]["key"], groups[1]["label"]), ("", None))

	def test_without_a_field_the_queue_is_one_group_with_no_heading(self):
		groups = group_requests([request("A", "Works", cost=10), request("B", "Estates", cost=5)], None)
		self.assertEqual(len(groups), 1)
		self.assertEqual(groups[0]["key"], "")
		self.assertIsNone(groups[0]["value"])
		self.assertIsNone(groups[0]["label"])
		self.assertEqual(groups[0]["requests"], ["A", "B"])
		self.assertEqual(groups[0]["estimate"], 15)

	def test_a_linked_title_is_the_label_where_the_doctype_shows_titles(self):
		with patch.object(api, "_link_titles", return_value={"D-1": "Works"}):
			groups = group_requests([request("A", "D-1")], DEPARTMENT)
		self.assertEqual((groups[0]["value"], groups[0]["label"]), ("D-1", "Works"))


class TestGroupByField(TestCase):
	"""Which field the setting names, as the meta says it is."""

	def field(self, stored, *, fields=None):
		fields = {"department": DEPARTMENT} if fields is None else fields
		settings = frappe._dict() if stored is ... else frappe._dict(procurement_group_by=stored)
		meta = SimpleNamespace(get_field=lambda name: fields.get(name))
		with (
			patch.object(api, "_settings", return_value=settings),
			patch.object(api.frappe, "get_meta", return_value=meta),
		):
			return api.group_by_field()

	def test_a_site_that_never_said_groups_by_department(self):
		self.assertIs(self.field(...), DEPARTMENT)

	def test_a_site_that_cleared_it_has_one_list(self):
		self.assertIsNone(self.field(""))
		self.assertIsNone(self.field("  "))

	def test_a_field_the_doctype_does_not_have_is_one_list_not_an_error(self):
		self.assertIsNone(self.field("cost_centre"))

	def test_a_field_with_no_value_to_group_by_is_one_list(self):
		table = SimpleNamespace(fieldname="items", fieldtype="Table", label="Items")
		self.assertIsNone(self.field("items", fields={"items": table}))

	def test_any_other_field_the_site_names(self):
		company = SimpleNamespace(fieldname="company", fieldtype="Link", options="Company", label="Company")
		self.assertIs(self.field("company", fields={"company": company}), company)


class TestApproverCandidates(TestCase):
	"""Holders of submit, sorted by name -- nobody's approver fields promoted."""

	def candidates(self, rows, filters=None):
		qb = MagicMock()
		qb.from_.return_value.join.return_value.on.return_value.select.return_value.distinct.return_value.where.return_value.run.return_value = rows
		with (
			patch.object(api.PROCUREMENT, "require_available"),
			patch.object(api.frappe, "has_permission", return_value=True),
			patch.object(api, "_roles_that_may_approve", return_value={"Purchase Manager"}),
			patch.object(api.frappe, "qb", qb),
			patch.object(api, "session_employee") as session_employee,
		):
			found = get_procurement_approvers("User", "", "name", 0, 20, filters or {})
		# Who is asking changes nothing about who could decide.
		session_employee.assert_not_called()
		return found

	def test_sorted_by_full_name_case_blind(self):
		rows = (("z@example.com", "anna"), ("a@example.com", "Zed"), ("m@example.com", None))
		self.assertEqual(
			[row[0] for row in self.candidates(rows)],
			["z@example.com", "m@example.com", "a@example.com"],
		)

	def test_an_employee_in_the_filters_is_ignored(self):
		rows = (("b@example.com", "B"), ("a@example.com", "A"))
		self.assertEqual(
			self.candidates(rows, {"employee": "EMP-1"}),
			[("a@example.com", "A"), ("b@example.com", "B")],
		)

	def test_no_role_with_submit_is_nobody(self):
		with (
			patch.object(api.PROCUREMENT, "require_available"),
			patch.object(api.frappe, "has_permission", return_value=True),
			patch.object(api, "_roles_that_may_approve", return_value=set()),
		):
			self.assertEqual(get_procurement_approvers("User", "", "name", 0, 20, {}), [])
