"""Keeping the Bikram Sambat calendar current without anyone having to.

Bikram Sambat month lengths cannot be computed: Nepal's Panchanga Nirnayak
Samiti fixes each year and publishes it, as a PDF, a few months ahead. Every
converter therefore carries a table, and a table nobody updates goes wrong the
first time a published year differs from the guess that stood in for it -- which
is how this app came to show some 2081-2083 dates a day early.

So the table is not this app's to maintain. Its numbers come from
opensource-nepal's `nepali` package, whose maintainers have put each new year's
published lengths into it shortly before the year began (2081 on 5 March 2024,
2082 on 3 April 2025). Only the numbers: `refresh` reads the file they live in
from the project's repository each week and parses it as data
(`ast.literal_eval`). None of the package's code is installed, imported or run,
and this app has no dependency on it. A correction there reaches the site within
a week, without a release or a `bench update`.

Until the first fetch succeeds -- and whenever none has -- the browser converts
with the table this app ships (`calendar_data.js`), which holds the same numbers
as of October 2026.

What is fetched is checked before use -- see `validate` -- against the shape any
real calendar has and against the dates the government has published (the
shared `confirmed_dates.json`). A table that fails is not used, and nothing is
lost by that: the browser goes on converting with the last good one.

Nothing here needs a person except when something has changed or gone wrong;
then System Managers get a ToDo saying so.

The browser does the converting (`commons/sambat/js/`); what it is
sent at boot is `boot_calendar()`.
"""

import ast
import functools
import json
import re
from datetime import date, timedelta

import frappe
import requests
from frappe.utils import escape_html, getdate, today

from commons.commons_core import settings

# The file the `nepali` package's converter lives in, on its default branch.
UPSTREAM = "https://raw.githubusercontent.com/opensource-nepal/py-nepali/main/nepali/date_converter.py"
UPSTREAM_NAME = "opensource-nepal/py-nepali"

# Commons Settings: the calendar in use, as JSON, and the line the form shows about it.
CALENDAR_FIELD = "bikram_sambat_calendar"
STATUS_FIELD = "bikram_sambat_calendar_status"

# How long the weekly check may go on failing before someone is told.
STALE_AFTER = timedelta(days=45)

MONTHS = (
	"Baisakh",
	"Jestha",
	"Asar",
	"Shrawan",
	"Bhadra",
	"Asoj",
	"Kartik",
	"Mangsir",
	"Poush",
	"Magh",
	"Falgun",
	"Chaitra",
)

# What a calendar is, as opposed to what this module records about it.
CALENDAR_KEYS = ("first_year", "epoch", "months")


# Reading
# -------


def parse(source: str) -> dict:
	"""The calendar in opensource-nepal's `date_converter.py`, read as data.

	Three class attributes of `NepaliDateConverter`: the first year, the
	Gregorian date it began, and one `((twelve month lengths), total)` per year.
	`ast.literal_eval` accepts literals and nothing else, so a file that had
	changed into something other than data is refused rather than run.

	Raises ValueError for anything that is not a usable calendar.
	"""
	try:
		tree = ast.parse(source)
	except SyntaxError as error:
		raise ValueError(f"the file is not Python ({error.msg})") from error

	found = {}
	for node in ast.walk(tree):
		if isinstance(node, ast.ClassDef) and node.name == "NepaliDateConverter":
			for statement in node.body:
				if (
					isinstance(statement, ast.Assign)
					and len(statement.targets) == 1
					and isinstance(statement.targets[0], ast.Name)
				):
					found[statement.targets[0].id] = statement.value

	try:
		calendar = {
			"first_year": ast.literal_eval(found["NP_INITIAL_YEAR"]),
			"epoch": date(*ast.literal_eval(found["REFERENCE_EN_DATE"])).isoformat(),
			"months": [list(row[0]) for row in ast.literal_eval(found["NP_MONTHS_DATA"])],
		}
	except KeyError as error:
		raise ValueError(f"NepaliDateConverter has no {error.args[0]}") from error
	except (ValueError, TypeError, IndexError) as error:
		raise ValueError(f"the calendar is not in the expected shape ({error})") from error
	return validate(calendar)


def shipped() -> dict:
	"""The table this app ships for the browser, read out of `calendar_data.js`.

	What the browser falls back to, and so what a first fetch is compared with to
	say what changed. Read rather than copied, so there is still one shipped table.
	"""
	path = frappe.get_app_path("commons", "sambat", "js", "calendar_data.js")
	with open(path) as file:
		source = file.read()
	first_year = int(re.search(r"FIRST_BS_YEAR = (\d+);", source).group(1))
	year, month, day = map(int, re.search(r"Date\.UTC\((\d+), (\d+), (\d+)\)", source).groups())
	return {
		"first_year": first_year,
		# JavaScript counts months from 0.
		"epoch": date(year, month + 1, day).isoformat(),
		"months": [[int(character) + 28 for character in row] for row in re.findall(r'"(\d{12})"', source)],
	}


def stored() -> dict | None:
	"""What the weekly check last saved, with its `checked` and `changed` dates, or None."""
	raw = settings.value(CALENDAR_FIELD)
	if not raw:
		return None
	try:
		record = json.loads(raw) if isinstance(raw, str) else raw
		validate(record)
	except (ValueError, TypeError):
		return None
	return record


def current() -> dict | None:
	"""The last calendar fetched, or None while there is none and the shipped table answers."""
	return calendar_of(stored())


def boot_calendar() -> dict | None:
	"""What the browser is sent. None leaves it on the table this app ships."""
	return current()


def calendar_of(record: dict | None) -> dict | None:
	"""Just the calendar, without what this module records about it."""
	return {key: record[key] for key in CALENDAR_KEYS} if record else None


# Checking
# --------


def validate(calendar: dict) -> dict:
	"""The calendar, if it could be real and agrees with what has been published.

	* every month is 29 to 32 days, and every year 365 or 366;
	* every year begins between 10 and 16 April -- a slip in one row would push
	  every later new year out of that window, so this catches a table that is
	  wrong by a day as well as one that is badly broken;
	* it covers today and all of next year, so a truncated file is not taken for
	  a calendar that ends early;
	* it puts every date in `confirmed_dates.json` where the government did.

	Raises ValueError saying which.
	"""
	first_year = calendar.get("first_year")
	months = calendar.get("months")
	if not isinstance(first_year, int) or not isinstance(months, list) or not months:
		raise ValueError("it has no years")
	for offset, row in enumerate(months):
		year = first_year + offset
		if not (isinstance(row, list) and len(row) == 12 and all(isinstance(days, int) for days in row)):
			raise ValueError(f"BS {year} is not twelve month lengths")
		if not all(29 <= days <= 32 for days in row) or sum(row) not in (365, 366):
			raise ValueError(f"BS {year} has months of {row}, which no year has")

	for year, start in zip(range(first_year, first_year + len(months)), year_starts(calendar), strict=True):
		if not (start.month == 4 and 10 <= start.day <= 16):
			raise ValueError(f"BS {year} would begin on {start}, not in mid-April")

	this_year = from_gregorian(calendar, getdate(today()))
	if not this_year or this_year[0] + 1 > first_year + len(months) - 1:
		raise ValueError("it does not reach the end of next year")

	for confirmed in confirmed_dates():
		year, month, day = (int(part) for part in confirmed["bs"].split("-"))
		if not first_year <= year < first_year + len(months):
			continue
		found = to_gregorian(calendar, year, month, day)
		if found != getdate(confirmed["ad"]):
			raise ValueError(
				f"it puts {confirmed['what']}, BS {confirmed['bs']}, on {found} "
				f"where {confirmed['source']} has {confirmed['ad']}"
			)
	return calendar


@functools.cache
def confirmed_dates() -> tuple:
	"""Dates the government has published in both calendars. Shared with the browser's tests."""
	path = frappe.get_app_path("commons", "sambat", "js", "confirmed_dates.json")
	with open(path) as file:
		return tuple(json.load(file))


# Converting, for the checks above. The browser has its own, over the same table.


def year_starts(calendar: dict) -> list[date]:
	start = getdate(calendar["epoch"])
	starts = []
	for row in calendar["months"]:
		starts.append(start)
		start += timedelta(days=sum(row))
	return starts


def to_gregorian(calendar: dict, year: int, month: int, day: int) -> date | None:
	offset = year - calendar["first_year"]
	if not 0 <= offset < len(calendar["months"]) or not 1 <= month <= 12:
		return None
	row = calendar["months"][offset]
	if not 1 <= day <= row[month - 1]:
		return None
	return year_starts(calendar)[offset] + timedelta(days=sum(row[: month - 1]) + day - 1)


def from_gregorian(calendar: dict, when: date) -> tuple[int, int, int] | None:
	for offset, start in enumerate(year_starts(calendar)):
		row = calendar["months"][offset]
		remaining = (when - start).days
		if 0 <= remaining < sum(row):
			for month, length in enumerate(row, start=1):
				if remaining < length:
					return (calendar["first_year"] + offset, month, remaining + 1)
				remaining -= length
	return None


def changes(old: dict, new: dict) -> list[str]:
	"""What differs between two calendars, a line per month or year.

	Only in the years they share, plus any the new one has dropped at the end:
	years before its first are kept from the shipped table by the browser, and
	years added at the end only mean dates that showed nothing now show one.
	"""

	def by_year(calendar):
		years = range(calendar["first_year"], calendar["first_year"] + len(calendar["months"]))
		return dict(zip(years, zip(year_starts(calendar), calendar["months"], strict=True), strict=True))

	old_years, new_years = by_year(old), by_year(new)
	lines = []
	for year, (start, after) in new_years.items():
		if year not in old_years:
			continue
		old_start, before = old_years[year]
		if start != old_start:
			lines.append(f"BS {year} now begins on {start}, not {old_start}")
		lines.extend(
			f"BS {year} {name}: {a} → {b} days"
			for name, a, b in zip(MONTHS, before, after, strict=True)
			if a != b
		)
	lines.extend(f"BS {year} removed" for year in old_years if year > max(new_years))
	return lines


# The weekly check
# ----------------


def refresh() -> None:
	"""Fetch opensource-nepal's calendar and use it if it is good. Weekly, from `hooks.py`.

	Unchanged, it only records the check. Changed, it is saved, every user's
	cached boot is dropped so the next page load converts with it, and System
	Managers are told what moved. Unusable, it is ignored and they are told why;
	unreachable for longer than `STALE_AFTER`, they are told that too.
	"""
	if not settings.feature_enabled(settings.ENABLE_BIKRAM_SAMBAT):
		return

	record = stored()
	try:
		response = requests.get(UPSTREAM, timeout=30)
		response.raise_for_status()
		fetched = parse(response.text)
	except requests.RequestException:
		checked = getdate(record["checked"]) if record and record.get("checked") else None
		if checked and getdate(today()) - checked > STALE_AFTER:
			tell(
				f"Commons has not been able to fetch the Bikram Sambat calendar from {UPSTREAM_NAME} "
				f"since {checked}. Dates still convert with the calendar it last had, which may "
				"miss corrections made since.",
				once=True,
			)
		return
	except ValueError as error:
		tell(
			f"The Bikram Sambat calendar from {UPSTREAM_NAME} was not used, because {error}. "
			"Dates still convert with the calendar Commons already had.",
			once=True,
		)
		return

	lines = changes(current() or shipped(), fetched)
	save(fetched, changed=today() if calendar_of(record) != fetched else None, previous=record)
	if lines:
		tell(
			f"The Bikram Sambat calendar was updated from {UPSTREAM_NAME}. "
			"These are the differences from the calendar it replaces:",
			lines,
		)


def save(calendar: dict, changed: str | None, previous: dict | None) -> None:
	record = {
		**calendar,
		"source": UPSTREAM_NAME,
		"checked": today(),
		"changed": changed or (previous or {}).get("changed"),
	}
	last_year = calendar["first_year"] + len(calendar["months"]) - 1
	status = (
		f"From {UPSTREAM_NAME}: BS {calendar['first_year']} to {last_year}. "
		f"Checked {record['checked']}; last changed {record['changed']}."
	)
	frappe.db.set_single_value(
		settings.SETTINGS,
		{CALENDAR_FIELD: json.dumps(record), STATUS_FIELD: status},
		update_modified=False,
	)
	if calendar_of(previous) != calendar:
		# Every user's boot carries the calendar; drop them so it is read afresh.
		frappe.cache.delete_key("bootinfo")


def tell(message: str, lines: list[str] | None = None, once: bool = False) -> None:
	"""A ToDo on Commons Settings for each System Manager.

	`once` skips anyone who still has the same one open, so a check that fails
	every week says so once rather than every week.
	"""
	description = f"<p>{escape_html(message)}</p>"
	if lines:
		shown = lines[:24]
		more = f"<li>and {len(lines) - len(shown)} more</li>" if len(lines) > len(shown) else ""
		description += "<ul>" + "".join(f"<li>{escape_html(line)}</li>" for line in shown) + more + "</ul>"

	managers = frappe.get_all(
		"Has Role", filters={"role": "System Manager", "parenttype": "User"}, pluck="parent"
	)
	users = frappe.get_all(
		"User",
		filters=[
			["name", "in", managers or [""]],
			["name", "not in", ["Administrator", "Guest"]],
			["enabled", "=", 1],
			["user_type", "=", "System User"],
		],
		pluck="name",
	)
	for user in users:
		if once and frappe.db.exists(
			"ToDo",
			{
				"allocated_to": user,
				"status": "Open",
				"reference_type": settings.SETTINGS,
				"description": description,
			},
		):
			continue
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": user,
				"description": description,
				"reference_type": settings.SETTINGS,
				"reference_name": settings.SETTINGS,
			}
		).insert(ignore_permissions=True)
