"""Reading opensource-nepal's calendar as data, refusing what is not one, and the weekly check.

No site and no network: the upstream file is built here from the shipped table,
which holds the same numbers, and the fetch, the settings and the ToDos are
stood in for.
"""

from unittest import TestCase
from unittest.mock import patch

import requests

from commons.sambat import table

TODAY = "2026-10-09"


def upstream_source(calendar: dict, first_year: int | None = None, epoch=(1943, 4, 14)) -> str:
	"""A `date_converter.py` the way opensource-nepal writes it, holding `calendar`'s years."""
	rows = [(tuple(row), sum(row)) for row in calendar["months"]]
	return (
		"class NepaliDateConverter:\n"
		f"    NP_INITIAL_YEAR = {first_year or calendar['first_year']}\n"
		f"    REFERENCE_EN_DATE = {epoch!r}\n"
		f"    NP_MONTHS_DATA = {rows!r}\n"
		"\n"
		"    def english_to_nepali(self, year, month, day):\n"
		"        raise NotImplementedError\n"
	)


def from_two_thousand() -> dict:
	shipped = table.shipped()
	return {
		"first_year": 2000,
		"epoch": "1943-04-14",
		"months": [row[:] for row in shipped["months"][2000 - shipped["first_year"] :]],
	}


class Base(TestCase):
	def setUp(self):
		self.enterContext(patch.object(table, "today", return_value=TODAY))


class TestReading(Base):
	def test_reads_the_calendar_out_of_the_file(self):
		calendar = from_two_thousand()
		self.assertEqual(table.parse(upstream_source(calendar)), calendar)

	def test_the_shipped_table_is_a_calendar_too(self):
		shipped = table.shipped()
		self.assertEqual((shipped["first_year"], shipped["epoch"]), (1970, "1913-04-13"))
		self.assertEqual(len(shipped["months"]), 2095 - 1970 + 1)
		table.validate(shipped)

	def test_refuses_anything_that_would_have_to_run(self):
		source = upstream_source(from_two_thousand()).replace(
			"NP_MONTHS_DATA = [", "NP_MONTHS_DATA = load() or ["
		)
		with self.assertRaises(ValueError):
			table.parse(source)

	def test_refuses_a_file_without_the_calendar(self):
		with self.assertRaisesRegex(ValueError, "has no"):
			table.parse("class NepaliDateConverter:\n    NP_INITIAL_YEAR = 2000\n")
		with self.assertRaisesRegex(ValueError, "not Python"):
			table.parse("<html>Not Found</html>")


class TestValidating(Base):
	def test_a_month_no_calendar_has(self):
		calendar = from_two_thousand()
		calendar["months"][50][3] = 33
		with self.assertRaisesRegex(ValueError, "BS 2050"):
			table.validate(calendar)

	def test_a_new_year_out_of_mid_april(self):
		calendar = {**from_two_thousand(), "epoch": "1943-04-24"}
		with self.assertRaisesRegex(ValueError, "mid-April"):
			table.validate(calendar)

	def test_a_day_out_against_what_the_government_published(self):
		calendar = from_two_thousand()
		# A day from Kartik into Mangsir in 2082: every year still the right
		# length, but Udhauli, Mangsir 18, lands a day early.
		calendar["months"][82][6] -= 1
		calendar["months"][82][7] += 1
		with self.assertRaisesRegex(ValueError, "Udhauli"):
			table.validate(calendar)

	def test_a_file_cut_short(self):
		calendar = from_two_thousand()
		calendar["months"] = calendar["months"][: 2083 - 2000 + 1]
		with self.assertRaisesRegex(ValueError, "next year"):
			table.validate(calendar)


class TestChanges(Base):
	def test_nothing_when_only_the_early_years_differ(self):
		self.assertEqual(table.changes(table.shipped(), from_two_thousand()), [])

	def test_each_month_that_moved(self):
		changed = from_two_thousand()
		changed["months"][84][6] -= 1
		changed["months"][84][7] += 1
		self.assertEqual(
			table.changes(table.shipped(), changed),
			["BS 2084 Kartik: 30 → 29 days", "BS 2084 Mangsir: 30 → 31 days"],
		)

	def test_a_year_that_now_begins_on_another_day(self):
		changed = from_two_thousand()
		changed["months"][84][11] += 1
		changed["months"][85][0] -= 1
		lines = table.changes(from_two_thousand(), changed)
		self.assertIn("BS 2085 now begins on 2028-04-15, not 2028-04-14", lines)


class TestRefresh(Base):
	def setUp(self):
		super().setUp()
		self.enterContext(patch.object(table.settings, "feature_enabled", return_value=True))
		self.saved = self.enterContext(patch.object(table, "save"))
		self.told = self.enterContext(patch.object(table, "tell"))
		self.record = None
		self.enterContext(patch.object(table, "stored", side_effect=lambda: self.record))

	def fetch(self, text=None, error=None):
		response = patch.object(table.requests, "get")
		get = self.enterContext(response)
		if error:
			get.side_effect = error
		else:
			get.return_value.text = text
		table.refresh()

	def test_does_nothing_where_bikram_sambat_is_off(self):
		with patch.object(table.settings, "feature_enabled", return_value=False):
			self.fetch(error=AssertionError("fetched"))
		self.saved.assert_not_called()

	def test_a_first_fetch_matching_the_shipped_table_is_kept_quietly(self):
		calendar = from_two_thousand()
		self.fetch(upstream_source(calendar))
		self.saved.assert_called_once_with(calendar, changed=TODAY, previous=None)
		self.told.assert_not_called()

	def test_a_change_is_kept_and_told(self):
		self.record = {**from_two_thousand(), "checked": "2026-10-02", "changed": "2026-09-01"}
		changed = from_two_thousand()
		changed["months"][84][6] -= 1
		changed["months"][84][7] += 1
		self.fetch(upstream_source(changed))
		self.saved.assert_called_once_with(changed, changed=TODAY, previous=self.record)
		message, lines = self.told.call_args.args
		self.assertIn("updated", message)
		self.assertEqual(lines, ["BS 2084 Kartik: 30 → 29 days", "BS 2084 Mangsir: 30 → 31 days"])

	def test_an_unchanged_fetch_only_records_the_check(self):
		self.record = {**from_two_thousand(), "checked": "2026-10-02", "changed": "2026-09-01"}
		self.fetch(upstream_source(from_two_thousand()))
		self.saved.assert_called_once_with(from_two_thousand(), changed=None, previous=self.record)
		self.told.assert_not_called()

	def test_a_bad_calendar_is_not_used_and_is_told_once(self):
		broken = from_two_thousand()
		broken["months"][82][6] -= 1
		broken["months"][82][7] += 1
		self.fetch(upstream_source(broken))
		self.saved.assert_not_called()
		self.assertIn("Udhauli", self.told.call_args.args[0])
		self.assertTrue(self.told.call_args.kwargs["once"])

	def test_a_short_outage_is_not_told(self):
		self.record = {**from_two_thousand(), "checked": "2026-09-20", "changed": "2026-09-01"}
		self.fetch(error=requests.ConnectionError())
		self.told.assert_not_called()
		self.saved.assert_not_called()

	def test_a_long_outage_is(self):
		self.record = {**from_two_thousand(), "checked": "2026-08-01", "changed": "2026-08-01"}
		self.fetch(error=requests.ConnectionError())
		self.assertIn("since 2026-08-01", self.told.call_args.args[0])
		self.assertTrue(self.told.call_args.kwargs["once"])


class TestQueueing(TestCase):
	"""Fetching straight after a migrate, and as soon as the setting is ticked."""

	def setUp(self):
		self.enqueue = self.enterContext(patch.object(table.frappe, "enqueue"))

	def settings_doc(self, on, was_on):
		before = None if was_on is None else {table.settings.ENABLE_BIKRAM_SAMBAT: was_on}
		doc = {table.settings.ENABLE_BIKRAM_SAMBAT: on}
		return type(
			"Doc",
			(),
			{"get": lambda self, key: doc.get(key), "get_doc_before_save": lambda self: before},
		)()

	def test_after_migrate_where_bikram_sambat_is_on(self):
		with patch.object(table.settings, "feature_enabled", return_value=True):
			table.queue_refresh()
		self.enqueue.assert_called_once()
		self.assertEqual(self.enqueue.call_args.args[0], "commons.sambat.table.refresh")
		self.assertTrue(self.enqueue.call_args.kwargs["deduplicate"])
		self.assertTrue(self.enqueue.call_args.kwargs["enqueue_after_commit"])

	def test_not_after_migrate_where_it_is_off(self):
		with patch.object(table.settings, "feature_enabled", return_value=False):
			table.queue_refresh()
		self.enqueue.assert_not_called()

	def test_when_the_setting_is_ticked(self):
		table.refresh_when_switched_on(self.settings_doc(on=1, was_on=0))
		table.refresh_when_switched_on(self.settings_doc(on=1, was_on=None))
		self.assertEqual(self.enqueue.call_count, 2)

	def test_not_on_every_save_while_it_stays_on_or_off(self):
		table.refresh_when_switched_on(self.settings_doc(on=1, was_on=1))
		table.refresh_when_switched_on(self.settings_doc(on=0, was_on=1))
		table.refresh_when_switched_on(self.settings_doc(on=0, was_on=0))
		self.enqueue.assert_not_called()

	def test_a_queue_that_cannot_be_reached_does_not_fail_the_migrate(self):
		self.enqueue.side_effect = ConnectionError("redis")
		with (
			patch.object(table.settings, "feature_enabled", return_value=True),
			patch.object(table.frappe, "log_error") as logged,
		):
			table.queue_refresh()
		logged.assert_called_once()
