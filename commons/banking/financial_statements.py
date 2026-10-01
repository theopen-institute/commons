"""ERPNext's financial statements: a column per fiscal year, and internal accounts left out.

Two overrides of `erpnext.accounts.report.financial_statements`, the module
behind Profit and Loss, the Balance Sheet, Cash Flow and the other reports that
lay periods out as columns. Each has its own switch in Commons Settings.

Fiscal year columns
-------------------
ERPNext cuts the columns by stepping whole calendar months from the first
year's start date, and never asks where each fiscal year ends. Bikram Sambat
years start mid-July on a date that moves by a day or two, so Nepal 2082/83
(16 July 2025 to 16 July 2026) and Nepal 2083/84 (17 July 2026 to 16 July 2027)
come out as three "years": 16 July to 15 July twice, then 16 July 2027 alone,
labelled "2027". A column's key is its end date's month, so the second and
third columns share `jul_2027`; both show the sum of the two, which is the
second column's figures twice. Each column but the last is also off by a day
from the year it stands for.

With "Enable Fiscal Year Columns", a report filtered by Fiscal Year has its
periods cut inside each fiscal year instead: a Yearly column is exactly one
year, labelled with the year's name, and a monthly, quarterly or half-yearly
column never crosses a year's end. Months are stepped from the year's start,
so a year that ends a day or two past its start's anniversary leaves a stub;
one shorter than `STUB_DAYS` is folded into the period before it rather than
standing as a column of its own. The years are walked from the start year to
the end year, each starting the day after the last ends. When they don't
chain like that (a gap, or two years starting the same day for this company)
the report keeps ERPNext's own periods. A Date Range filter always does.

Internal accounts
-----------------
An Account with "Internal Account" ticked records money moving between the
organisation's own departments rather than with anyone outside it -- one
department's internal charge is another's earned income. Profit and Loss and
the Gross and Net Profit Report then offer "Hide Internal Accounts", which
leaves such accounts, and every account under one that is a group, out of the
report before anything is added up. Their parents' totals, the income and
expense totals and the net profit are then what is left. Net profit only stays
the same when the internal income and expense net to nothing, which is up to
how they are booked; nothing here checks it.

How it is put in
----------------
Every report imports `get_period_list` and `get_data` by name, when it is
first run in a process. `install` replaces both on ERPNext's module before any
report has run, and rebinds the names in any module that has already imported
them. `get_data` finds `get_accounts` and `set_gl_entries_by_account` on the
module when it runs, so replacing those two there is enough. Process-wide and
idempotent: a worker serves every site on the bench, so each replacement reads
its own site's switch on every call, and with the switch off is exactly
ERPNext's. Called from `before_request` and `before_job`; a console session or
a test calls it itself.
"""

import contextvars
import inspect
import sys

import frappe
from frappe.utils import add_days, add_months, date_diff, formatdate, getdate

from commons.commons_core.settings import (
	ENABLE_FISCAL_YEAR_COLUMNS,
	ENABLE_HIDING_INTERNAL_ACCOUNTS,
	feature_enabled,
)

# The Account field, from `commons/fixtures/custom_field_erpnext.json`, and the
# report filter `commons/public/js/hide_internal_accounts.js` adds.
INTERNAL_ACCOUNT = "internal_account"
HIDE_INTERNAL_ACCOUNTS = "hide_internal_accounts"

# A period at a year's end shorter than this is part of the one before it.
STUB_DAYS = 7

MONTHS_PER_PERIOD = {"Yearly": 12, "Half-Yearly": 6, "Quarterly": 3, "Monthly": 1}

# ERPNext's functions as this was written against them. If an upgrade changes
# one, nothing is replaced and the reports are ERPNext's own, said once.
EXPECTED = {
	"get_period_list": (
		"from_fiscal_year",
		"to_fiscal_year",
		"period_start_date",
		"period_end_date",
		"filter_based_on",
		"periodicity",
		"accumulated_values",
		"company",
		"reset_period_on_fy_change",
		"ignore_fiscal_year",
	),
	"get_data": (
		"company",
		"root_type",
		"balance_must_be",
		"period_list",
		"filters",
		"accumulated_values",
		"only_current_fiscal_year",
		"ignore_closing_entries",
		"ignore_accumulated_values_for_fy",
		"total",
	),
	"get_accounts": ("company", "root_type"),
	"get_label": ("periodicity", "from_date", "to_date"),
	"set_gl_entries_by_account": None,
}
# What `get_data` must still look up on the module for the hiding to reach it.
GET_DATA_CALLS = ("get_accounts", "set_gl_entries_by_account")

# The accounts the `get_data` running in this context leaves out, if any.
_hidden: contextvars.ContextVar[frozenset | None] = contextvars.ContextVar(
	"commons_hidden_accounts", default=None
)
_originals: dict = {}
_refused: str | None = None


def install() -> None:
	"""Put this module's functions where ERPNext's reports look for theirs."""
	global _refused

	if _originals or _refused:
		return
	try:
		from erpnext.accounts.report import financial_statements as fs
	except ImportError:
		# No ERPNext on this bench: nothing to override, and nothing to say.
		_refused = "ERPNext is not installed"
		return

	if problems := incompatibilities(fs):
		_refused = "; ".join(problems)
		frappe.logger("commons").warning(f"Financial statement overrides not installed: {_refused}")
		return

	replacements = {
		"get_period_list": get_period_list,
		"get_data": get_data,
		"get_accounts": get_accounts,
		"set_gl_entries_by_account": set_gl_entries_by_account,
	}
	for name, replacement in replacements.items():
		original = getattr(fs, name)
		_originals[name] = original
		setattr(fs, name, replacement)
		if name in GET_DATA_CALLS:
			continue
		# A report already run in this process holds its own reference. Read
		# from each module's own namespace, which never imports anything.
		for module in list(sys.modules.values()):
			namespace = getattr(module, "__dict__", None)
			if namespace is not None and namespace.get(name) is original:
				namespace[name] = replacement
	_originals["get_label"] = fs.get_label


def incompatibilities(fs) -> list[str]:
	"""What about ERPNext's module no longer matches what this was written against."""
	problems = []
	for name, parameters in EXPECTED.items():
		function = getattr(fs, name, None)
		if not callable(function):
			problems.append(f"{name} is gone")
		elif parameters is not None and tuple(inspect.signature(function).parameters) != parameters:
			problems.append(f"{name} now takes {tuple(inspect.signature(function).parameters)}")
	get_data_function = getattr(fs, "get_data", None)
	if callable(get_data_function):
		for name in GET_DATA_CALLS:
			if name not in get_data_function.__code__.co_names:
				problems.append(f"get_data no longer calls {name}")
	return problems


# Fiscal year columns
# -------------------


def get_period_list(
	from_fiscal_year,
	to_fiscal_year,
	period_start_date,
	period_end_date,
	filter_based_on,
	periodicity,
	accumulated_values=False,
	company=None,
	reset_period_on_fy_change=True,
	ignore_fiscal_year=False,
):
	"""ERPNext's `get_period_list`, with each fiscal year's periods inside it."""
	if filter_based_on == "Fiscal Year" and feature_enabled(ENABLE_FISCAL_YEAR_COLUMNS):
		if years := fiscal_years_between(from_fiscal_year, to_fiscal_year, company):
			return fiscal_year_periods(
				years,
				periodicity,
				accumulated_values=accumulated_values,
				reset_period_on_fy_change=reset_period_on_fy_change,
				ignore_fiscal_year=ignore_fiscal_year,
			)
	return _originals["get_period_list"](
		from_fiscal_year,
		to_fiscal_year,
		period_start_date,
		period_end_date,
		filter_based_on,
		periodicity,
		accumulated_values=accumulated_values,
		company=company,
		reset_period_on_fy_change=reset_period_on_fy_change,
		ignore_fiscal_year=ignore_fiscal_year,
	)


def fiscal_years_between(from_fiscal_year, to_fiscal_year, company=None) -> list:
	"""The fiscal years from one through the other, each starting the day after the
	last ends, or [] when they don't chain like that.

	A year that names companies only counts for those; one naming none counts for
	all, as ERPNext reads it. Where two years start on the same day, the end year
	is taken if it is one of them; otherwise the chain is ambiguous, and [].
	"""
	if not from_fiscal_year or not to_fiscal_year:
		return []
	first = frappe.db.get_value(
		"Fiscal Year", from_fiscal_year, ["name", "year_start_date", "year_end_date"], as_dict=True
	)
	last = frappe.db.get_value(
		"Fiscal Year", to_fiscal_year, ["name", "year_start_date", "year_end_date"], as_dict=True
	)
	if not first or not last or getdate(last.year_end_date) < getdate(first.year_start_date):
		# ERPNext's own says why.
		return []

	years = frappe.get_all(
		"Fiscal Year",
		filters={
			"year_start_date": (">=", first.year_start_date),
			"year_end_date": ("<=", last.year_end_date),
			"disabled": 0,
		},
		fields=["name", "year_start_date", "year_end_date"],
		order_by="year_start_date",
	)
	if company:
		companies = {}
		for row in frappe.get_all(
			"Fiscal Year Company",
			filters={"parenttype": "Fiscal Year", "parent": ("in", [y.name for y in years])},
			fields=["parent", "company"],
		):
			companies.setdefault(row.parent, set()).add(row.company)
		years = [y for y in years if y.name not in companies or company in companies[y.name]]

	starting = {}
	for year in years:
		starting.setdefault(getdate(year.year_start_date), []).append(year)

	chain = [first]
	while chain[-1].name != last.name:
		candidates = starting.get(add_days(getdate(chain[-1].year_end_date), 1), [])
		named = [y for y in candidates if y.name == last.name]
		if named:
			chain.append(named[0])
		elif len(candidates) == 1:
			chain.append(candidates[0])
		else:
			return []
	return chain


def fiscal_year_periods(
	years,
	periodicity,
	accumulated_values=False,
	reset_period_on_fy_change=True,
	ignore_fiscal_year=False,
) -> list:
	"""The period list ERPNext's reports expect, cut inside each of `years`.

	Each period carries what ERPNext's own does: its dates, key and label, the
	whole range's first and last day, and unless `ignore_fiscal_year` the
	fiscal year its end falls in and the start of the one its start falls in.
	"""
	get_label = _originals["get_label"]
	months = MONTHS_PER_PERIOD[periodicity]

	cut = [(year, from_date, to_date) for year in years for from_date, to_date in periods_of(year, months)]
	year_start_date = getdate(years[0].year_start_date)
	year_end_date = getdate(years[-1].year_end_date)

	period_list = []
	keys = set()
	for year, from_date, to_date in cut:
		period = frappe._dict(from_date=from_date, to_date=to_date)
		if not ignore_fiscal_year:
			period.to_date_fiscal_year = year.name
			period.from_date_fiscal_year_start_date = getdate(year.year_start_date)

		key = to_date.strftime("%b_%Y").lower()
		if key in keys:
			# Two periods ending in one month: a stub that stood on its own.
			key = to_date.strftime("%d_%b_%Y").lower()
		keys.add(key)

		whole_year = from_date == getdate(year.year_start_date) and to_date == getdate(year.year_end_date)
		if periodicity == "Yearly" and whole_year:
			label = year.name
		elif periodicity == "Monthly" and not accumulated_values:
			label = formatdate(to_date, "MMM YYYY")
		elif not accumulated_values:
			label = get_label(periodicity, from_date, to_date)
		elif reset_period_on_fy_change:
			label = get_label(periodicity, getdate(year.year_start_date), to_date)
		else:
			label = get_label(periodicity, year_start_date, to_date)

		period.update(
			key=key,
			label=label,
			year_start_date=year_start_date,
			year_end_date=year_end_date,
		)
		period_list.append(period)
	return period_list


def periods_of(year, months: int) -> list[tuple]:
	"""(from, to) for each period of `months` months in one fiscal year.

	Stepped from the year's start rather than from the last period's end, so a
	start late in a month does not drift: 31 January, 28 February, 31 March.
	"""
	start, end = getdate(year.year_start_date), getdate(year.year_end_date)
	periods = []
	step = 1
	from_date = start
	while from_date <= end:
		to_date = min(add_days(add_months(start, months * step), -1), end)
		if periods and to_date == end and date_diff(to_date, from_date) + 1 < STUB_DAYS:
			periods[-1] = (periods[-1][0], end)
			break
		periods.append((from_date, to_date))
		from_date = add_days(to_date, 1)
		step += 1
	return periods


# Internal accounts
# -----------------


def get_data(
	company,
	root_type,
	balance_must_be,
	period_list,
	filters=None,
	accumulated_values=1,
	only_current_fiscal_year=True,
	ignore_closing_entries=False,
	ignore_accumulated_values_for_fy=False,
	total=True,
):
	"""ERPNext's `get_data`, without the internal accounts when the filter asks."""
	token = _hidden.set(hidden_accounts(company, root_type, filters))
	try:
		return _originals["get_data"](
			company,
			root_type,
			balance_must_be,
			period_list,
			filters=filters,
			accumulated_values=accumulated_values,
			only_current_fiscal_year=only_current_fiscal_year,
			ignore_closing_entries=ignore_closing_entries,
			ignore_accumulated_values_for_fy=ignore_accumulated_values_for_fy,
			total=total,
		)
	finally:
		_hidden.reset(token)


def hidden_accounts(company, root_type, filters) -> frozenset | None:
	"""The accounts of `root_type` a report with these filters leaves out: each
	internal account and everything under it. None when it leaves out nothing."""
	if not (filters and filters.get(HIDE_INTERNAL_ACCOUNTS)):
		return None
	if not feature_enabled(ENABLE_HIDING_INTERNAL_ACCOUNTS):
		return None
	# Code lands before the migrate that adds the field.
	if not frappe.get_meta("Account").has_field(INTERNAL_ACCOUNT):
		return None

	accounts = frappe.get_all(
		"Account",
		filters={"company": company, "root_type": root_type},
		fields=["name", "lft", "rgt", INTERNAL_ACCOUNT],
	)
	internal = [(a.lft, a.rgt) for a in accounts if a.get(INTERNAL_ACCOUNT)]
	if not internal:
		return None
	return frozenset(a.name for a in accounts if any(lft <= a.lft and a.rgt <= rgt for lft, rgt in internal))


def get_accounts(company, root_type):
	"""ERPNext's `get_accounts`, less the accounts being left out."""
	accounts = _originals["get_accounts"](company, root_type)
	hidden = _hidden.get()
	return [a for a in accounts if a.name not in hidden] if hidden else accounts


def set_gl_entries_by_account(*args, **kwargs):
	"""ERPNext's `set_gl_entries_by_account`, less the entries of the accounts being
	left out. It fetches by a root's lft and rgt, so it gets them all, and
	`calculate_values` refuses an entry whose account it was not given."""
	gl_entries_by_account = _originals["set_gl_entries_by_account"](*args, **kwargs)
	if hidden := _hidden.get():
		for account in hidden:
			gl_entries_by_account.pop(account, None)
	return gl_entries_by_account
