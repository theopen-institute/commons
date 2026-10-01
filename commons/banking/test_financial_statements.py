"""ERPNext's financial statements cut inside each fiscal year, and internal accounts left out, site-less.

What is pinned here is what would mislead quietly if it drifted: a Yearly
column is exactly one fiscal year and named for it, a stub of a day or two at a
year's end joins the column before it, the years are only chained when each
starts the day after the last ends, every period's key is its own, and an
internal group takes the accounts under it out with it. With either switch off
the reports are ERPNext's own.

Both were checked against a copy of a real site's Profit and Loss, with the
Nepal 2082/83 and 2083/84 years, in a console session.
"""

from datetime import date
from unittest import TestCase
from unittest.mock import patch

import frappe

from commons.banking import financial_statements as fs

NEPAL = [
	frappe._dict(name="Nepal 2081/82", year_start_date="2024-07-16", year_end_date="2025-07-15"),
	frappe._dict(name="Nepal 2082/83", year_start_date="2025-07-16", year_end_date="2026-07-16"),
	frappe._dict(name="Nepal 2083/84", year_start_date="2026-07-17", year_end_date="2027-07-16"),
]


def get_label(periodicity, from_date, to_date):
	return f"{periodicity} {from_date} {to_date}"


class TestPeriodsOfAYear(TestCase):
	def test_a_bikram_sambat_year_is_one_period(self):
		self.assertEqual(fs.periods_of(NEPAL[1], 12), [(date(2025, 7, 16), date(2026, 7, 16))])

	def test_its_last_month_takes_the_day_left_over(self):
		months = fs.periods_of(NEPAL[1], 1)
		self.assertEqual(len(months), 12)
		self.assertEqual(months[0], (date(2025, 7, 16), date(2025, 8, 15)))
		self.assertEqual(months[-1], (date(2026, 6, 16), date(2026, 7, 16)))

	def test_a_stub_of_a_week_or_more_stands_on_its_own(self):
		short = frappe._dict(name="Short", year_start_date="2025-01-15", year_end_date="2025-12-31")
		months = fs.periods_of(short, 1)
		self.assertEqual(months[-2], (date(2025, 11, 15), date(2025, 12, 14)))
		self.assertEqual(months[-1], (date(2025, 12, 15), date(2025, 12, 31)))

	def test_a_year_shorter_than_its_periodicity_is_one_period(self):
		short = frappe._dict(name="Short", year_start_date="2025-04-01", year_end_date="2025-12-31")
		self.assertEqual(fs.periods_of(short, 12), [(date(2025, 4, 1), date(2025, 12, 31))])

	def test_months_are_stepped_from_the_year_s_start(self):
		year = frappe._dict(name="Odd", year_start_date="2025-01-31", year_end_date="2026-01-30")
		ends = [to_date for _, to_date in fs.periods_of(year, 1)][:3]
		self.assertEqual(ends, [date(2025, 2, 27), date(2025, 3, 30), date(2025, 4, 29)])


@patch.dict(fs._originals, {"get_label": get_label})
class TestFiscalYearPeriods(TestCase):
	def test_one_column_per_year_named_for_it(self):
		periods = fs.fiscal_year_periods(NEPAL[1:], "Yearly")
		self.assertEqual([p.label for p in periods], ["Nepal 2082/83", "Nepal 2083/84"])
		self.assertEqual([p.key for p in periods], ["jul_2026", "jul_2027"])
		self.assertEqual(
			[(p.from_date, p.to_date) for p in periods],
			[(date(2025, 7, 16), date(2026, 7, 16)), (date(2026, 7, 17), date(2027, 7, 16))],
		)

	def test_each_period_knows_the_whole_range_and_its_own_year(self):
		periods = fs.fiscal_year_periods(NEPAL[1:], "Quarterly")
		self.assertEqual({p.year_start_date for p in periods}, {date(2025, 7, 16)})
		self.assertEqual({p.year_end_date for p in periods}, {date(2027, 7, 16)})
		self.assertEqual(periods[4].to_date_fiscal_year, "Nepal 2083/84")
		self.assertEqual(periods[4].from_date_fiscal_year_start_date, date(2026, 7, 17))

	def test_no_fiscal_year_keys_when_the_caller_ignores_them(self):
		period = fs.fiscal_year_periods(NEPAL[1:2], "Yearly", ignore_fiscal_year=True)[0]
		self.assertNotIn("to_date_fiscal_year", period)

	def test_no_two_periods_share_a_key(self):
		short = frappe._dict(name="Short", year_start_date="2025-01-15", year_end_date="2025-12-31")
		with patch.object(fs, "formatdate", side_effect=lambda d, fmt: str(d)):
			keys = [p.key for p in fs.fiscal_year_periods([short], "Monthly")]
		self.assertEqual(len(keys), len(set(keys)))
		self.assertEqual(keys[-2:], ["dec_2025", "31_dec_2025"])

	def test_accumulated_labels_count_from_the_period_s_own_year(self):
		periods = fs.fiscal_year_periods(NEPAL[1:], "Half-Yearly", accumulated_values=True)
		self.assertEqual(periods[2].label, "Half-Yearly 2026-07-17 2027-01-16")


def year_rows(*years):
	return [frappe._dict(y) for y in years]


class TestChainingYears(TestCase):
	def chain(self, years, companies=(), company=None, first="Nepal 2082/83", last="Nepal 2083/84"):
		by_name = {y.name: y for y in years}
		db = frappe._dict(get_value=lambda dt, name, *a, **k: by_name.get(name))
		with (
			patch.object(fs.frappe, "db", db),
			patch.object(
				fs.frappe,
				"get_all",
				side_effect=lambda doctype, **k: list(companies)
				if doctype == "Fiscal Year Company"
				else years,
			),
		):
			return [y.name for y in fs.fiscal_years_between(first, last, company)]

	def test_years_that_follow_one_another(self):
		self.assertEqual(self.chain(NEPAL), ["Nepal 2082/83", "Nepal 2083/84"])

	def test_a_gap_keeps_erpnext_s_periods(self):
		gap = year_rows({**NEPAL[1], "year_end_date": "2026-07-15"}, NEPAL[2])
		self.assertEqual(self.chain(gap), [])

	def test_another_company_s_year_starting_the_same_day_is_not_this_one_s(self):
		other = frappe._dict(name="Other 2083", year_start_date="2026-07-17", year_end_date="2027-07-16")
		companies = [frappe._dict(parent="Other 2083", company="Other Co")]
		years = [*NEPAL, other]
		self.assertEqual(
			self.chain(years, companies, company="Open Institute (Nepal)"), ["Nepal 2082/83", "Nepal 2083/84"]
		)

	def test_two_years_starting_the_same_day_take_the_end_year(self):
		other = frappe._dict(name="Other 2083", year_start_date="2026-07-17", year_end_date="2027-07-16")
		self.assertEqual(self.chain([*NEPAL, other]), ["Nepal 2082/83", "Nepal 2083/84"])

	def test_two_years_starting_the_same_day_in_the_middle_are_ambiguous(self):
		other = frappe._dict(name="Other 2082", year_start_date="2025-07-16", year_end_date="2026-07-16")
		years = [*NEPAL, other]
		self.assertEqual(self.chain(years, first="Nepal 2081/82", last="Nepal 2083/84"), [])

	def test_one_year(self):
		self.assertEqual(self.chain(NEPAL, last="Nepal 2082/83"), ["Nepal 2082/83"])


class TestSwitchedOff(TestCase):
	def test_erpnext_s_period_list_with_the_switch_off(self):
		original = patch.dict(fs._originals, {"get_period_list": lambda *a, **k: "erpnext"})
		with original, patch.object(fs, "feature_enabled", return_value=False):
			self.assertEqual(fs.get_period_list("a", "b", None, None, "Fiscal Year", "Yearly"), "erpnext")

	def test_erpnext_s_period_list_for_a_date_range(self):
		original = patch.dict(fs._originals, {"get_period_list": lambda *a, **k: "erpnext"})
		with original, patch.object(fs, "feature_enabled", return_value=True):
			self.assertEqual(
				fs.get_period_list(None, None, "2025-01-01", "2025-12-31", "Date Range", "Yearly"), "erpnext"
			)

	def test_nothing_hidden_without_the_filter(self):
		with patch.object(fs, "feature_enabled", return_value=True):
			self.assertIsNone(fs.hidden_accounts("Co", "Income", frappe._dict()))

	def test_nothing_hidden_with_the_switch_off(self):
		with patch.object(fs, "feature_enabled", return_value=False):
			self.assertIsNone(fs.hidden_accounts("Co", "Income", frappe._dict(hide_internal_accounts=1)))


ACCOUNTS = [
	frappe._dict(name="Income", lft=1, rgt=12, internal_account=0),
	frappe._dict(name="Fees", lft=2, rgt=3, internal_account=0),
	frappe._dict(name="Internal", lft=4, rgt=9, internal_account=1),
	frappe._dict(name="Earned", lft=5, rgt=6, internal_account=0),
	frappe._dict(name="Charged", lft=7, rgt=8, internal_account=0),
	frappe._dict(name="Earned (Internal)", lft=10, rgt=11, internal_account=1),
]


class FakeMeta:
	def has_field(self, fieldname):
		return True


class TestHiddenAccounts(TestCase):
	def hidden(self, accounts=ACCOUNTS):
		with (
			patch.object(fs, "feature_enabled", return_value=True),
			patch.object(fs.frappe, "get_meta", return_value=FakeMeta()),
			patch.object(fs.frappe, "get_all", return_value=accounts),
		):
			return fs.hidden_accounts("Co", "Income", frappe._dict(hide_internal_accounts=1))

	def test_an_internal_group_takes_its_accounts_with_it(self):
		self.assertEqual(self.hidden(), {"Internal", "Earned", "Charged", "Earned (Internal)"})

	def test_none_flagged_hides_nothing(self):
		self.assertIsNone(self.hidden([{**a, "internal_account": 0} for a in map(frappe._dict, ACCOUNTS)]))

	def test_the_accounts_and_their_entries_are_left_out_inside_get_data(self):
		hidden = frozenset({"Internal", "Earned"})
		seen = {}

		def get_data(*args, **kwargs):
			seen["accounts"] = [a.name for a in fs.get_accounts("Co", "Income")]
			seen["entries"] = sorted(fs.set_gl_entries_by_account({}))

		def gl_entries(gl_entries_by_account):
			gl_entries_by_account.update({"Fees": [1], "Earned": [2]})
			return gl_entries_by_account

		originals = {
			"get_data": get_data,
			"get_accounts": lambda company, root_type: [
				frappe._dict(name=n) for n in ("Income", "Fees", "Internal", "Earned")
			],
			"set_gl_entries_by_account": gl_entries,
		}
		with patch.dict(fs._originals, originals), patch.object(fs, "hidden_accounts", return_value=hidden):
			fs.get_data("Co", "Income", "Credit", [])
		self.assertEqual(seen, {"accounts": ["Income", "Fees"], "entries": ["Fees"]})
		# And outside it, nothing is.
		with patch.dict(fs._originals, originals):
			self.assertEqual(len(fs.get_accounts("Co", "Income")), 4)


class TestInstall(TestCase):
	def test_written_against_this_erpnext(self):
		from erpnext.accounts.report import financial_statements

		self.assertEqual(fs.incompatibilities(financial_statements), [])
