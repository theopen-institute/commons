"""What two sites must compute identically for Data Sync to work, site-less.

A hash that depends on how a value happened to come back from the database --
1 or 1.0, a blank column or a missing one, a rule's fields as text or a list --
would make every record look changed. These pin the canonical forms.

Loading, applying and deleting were checked on register.localhost: a round trip
of edit, stale refusal, restore, insert and delete through `api`, and the page
in a browser against a doctored snapshot and against the live endpoint.
"""

import datetime
from decimal import Decimal
from unittest import TestCase

from commons.data_sync import records, rules


def rule(**kwargs):
	return rules.normalise({"doctype": "Report", **kwargs})


class TestCanonicalValues(TestCase):
	def test_numbers_and_blanks(self):
		self.assertEqual(records.clean_value(1.0), 1)
		self.assertEqual(records.clean_value(Decimal("2.50")), 2.5)
		self.assertIsInstance(records.clean_value(Decimal("3")), int)
		self.assertIsNone(records.clean_value(""))
		self.assertIsNone(records.clean_value(None))
		self.assertEqual(records.clean_value(0), 0)

	def test_dates_become_text(self):
		self.assertEqual(records.clean_value(datetime.date(2026, 10, 6)), "2026-10-06")
		self.assertEqual(records.clean_value(datetime.timedelta(hours=1)), "1:00:00")


class TestHash(TestCase):
	def test_key_order_does_not_matter(self):
		r = rule()
		self.assertEqual(records.hash_of({"a": 1, "b": 2}, r), records.hash_of({"b": 2, "a": 1}, r))

	def test_ignored_fields_do_not_count(self):
		r = rule(ignored_fields="last_synced_on")
		self.assertEqual(
			records.hash_of({"a": 1, "last_synced_on": "x"}, r),
			records.hash_of({"a": 1, "last_synced_on": "y"}, r),
		)
		self.assertNotEqual(records.hash_of({"a": 1}, r), records.hash_of({"a": 2}, r))

	def test_child_order_counts(self):
		r = rule()
		one = {"roles": [{"role": "A", "idx": 1}, {"role": "B", "idx": 2}]}
		two = {"roles": [{"role": "B", "idx": 1}, {"role": "A", "idx": 2}]}
		self.assertNotEqual(records.hash_of(one, r), records.hash_of(two, r))


class TestKeys(TestCase):
	def test_name_by_default(self):
		self.assertEqual(records.record_key("Sales Invoice-foo", {}, rule()), "Sales Invoice-foo")

	def test_key_fields_compare_as_text(self):
		r = rule(key_fields="parent, role, permlevel, if_owner")
		as_int = records.record_key("x1", {"parent": "Item", "role": "R", "permlevel": 0, "if_owner": 0}, r)
		as_text = records.record_key(
			"x2", {"parent": "Item", "role": "R", "permlevel": "0", "if_owner": "0"}, r
		)
		self.assertEqual(as_int, as_text)


class TestRules(TestCase):
	def test_text_and_lists_normalise_alike(self):
		from_settings = rules.normalise(
			{
				"doctype": "Report",
				"filters": '{"is_standard": "No"}',
				"key_fields": "a, b",
				"ignored_fields": "c\nd",
			}
		)
		from_request = rules.normalise(
			{
				"doctype": "Report",
				"filters": {"is_standard": "No"},
				"key_fields": ["a", "b"],
				"ignored_fields": ["c", "d"],
			}
		)
		self.assertEqual(from_settings, from_request)

	def test_blank_filters_mean_none(self):
		self.assertIsNone(rules.normalise({"doctype": "Report", "filters": "  "})["filters"])

	def test_defaults_are_valid(self):
		for r in rules.DEFAULT_RULES:
			rules.normalise(r)

	def test_a_custom_role_is_known_by_its_page_or_report(self):
		"""Named by a hash, different on every site; one per page or report."""
		r = next(rules.normalise(r) for r in rules.DEFAULT_RULES if r["doctype"] == "Custom Role")
		here = records.record_key("a1b2c3", {"page": "commons-banking"}, r)
		there = records.record_key("d4e5f6", {"page": "commons-banking"}, r)
		self.assertEqual(here, there)
		report = records.record_key("a1b2c3", {"report": "Contact Hours Audit"}, r)
		self.assertNotEqual(here, report)

	def test_a_custom_role_comes_after_reports(self):
		order = [r["doctype"] for r in rules.DEFAULT_RULES]
		self.assertLess(order.index("Report"), order.index("Custom Role"))
