# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""The open ToDo list behind both of this app's To Do widgets.

Two front ends ask this module the same question: the staff portal's sidebar
(`frontend/src/data/todos.ts`) and the desk's (`commons/public/js/desk_todos.js`).
One answer for both, because a person crossing between the two all day must not
be shown two different numbers.

What "mine" means here is deliberately narrower than what the session user is
allowed to read:

    open ToDos allocated to me, plus open ToDos I created and never allocated.

`frappe.desk.doctype.todo.todo.get_permission_query_conditions` lets anyone
holding a ToDo role read *every* ToDo on the site, so a System Manager asking
for "my open ToDos" would otherwise be handed the whole organisation's backlog.
The user filter is applied explicitly rather than left to the permission layer.

Core's own `frappe.core.notifications.get_things_todo` is not that answer
either: it only counts, and it counts work handed to someone else as well.

This module lives here, and not in `frappe/`, for the reason every module in
this package does: a framework upgrade replaces that app wholesale. An earlier
version of this widget was written into `frappe/core/` and vanished on the bump
from 16.33.1 to 16.34.0.
"""

import datetime
import html
import re

import frappe
from frappe.utils import cint, getdate, strip_html, today

SORT_TYPES = ("due_date", "urgency", "doctype", "recent")
DEFAULT_SORT = "due_date"

# `priority` is a Select, so sorting it in SQL would give High, Low, Medium.
PRIORITY_RANK = {"High": 0, "Medium": 1, "Low": 2}

# Widest sensible list; both widgets link out to the full ToDo list beyond this.
MAX_ROWS = 100

LIST_FIELDS = (
	"name",
	"description",
	"status",
	"priority",
	"date",
	"color",
	"reference_type",
	"reference_name",
	"assigned_by",
	"allocated_to",
	"owner",
	"creation",
	"modified",
)

_WHITESPACE = re.compile(r"\s+")


def _mine_filter_sets() -> list[dict]:
	"""The two disjoint filter sets that together make up "my open ToDos".

	Two sets rather than one `or_filters` because the second arm is an AND
	(unallocated *and* created by me), which `or_filters` cannot express. They
	cannot overlap, one requiring `allocated_to` set to the user and the other
	requiring it unset, so the results concatenate without deduping.
	"""
	user = frappe.session.user
	return [
		{"status": "Open", "allocated_to": user},
		{"status": "Open", "allocated_to": ("is", "not set"), "owner": user},
	]


def get_open_todo_count() -> int:
	"""How many open ToDos belong to the session user."""
	return sum(frappe.db.count("ToDo", filters) for filters in _mine_filter_sets())


def _as_title(description: str | None) -> str:
	"""Flatten a Text Editor description into one line of plain text."""
	text = html.unescape(strip_html(description or ""))
	# a `&nbsp;` unescapes to U+00A0, which \s does not match on its own
	return _WHITESPACE.sub(" ", text.replace("\xa0", " ")).strip()


def _sorter(sort_by: str):
	"""Return `(key, reverse)` for the requested sort.

	Undated ToDos sort last wherever a due date is involved: an item with no
	deadline is not more urgent than one due today.
	"""
	no_date = datetime.date.max

	def due(todo):
		return getdate(todo.date) if todo.date else no_date

	def urgency(todo):
		return PRIORITY_RANK.get(todo.priority, len(PRIORITY_RANK))

	if sort_by == "urgency":
		return (lambda t: (urgency(t), due(t), t.name)), False

	if sort_by == "doctype":
		# the leading flag parks unlinked ToDos after every real doctype name
		return (
			lambda t: (
				not t.reference_type,
				(t.reference_type or "").lower(),
				(t.reference_name or "").lower(),
				due(t),
			)
		), False

	if sort_by == "recent":
		return (lambda t: (t.creation, t.name)), True

	return (lambda t: (due(t), urgency(t), t.name)), False


@frappe.whitelist()
def get_open_todos(sort_by: str = DEFAULT_SORT, limit: int | str = MAX_ROWS) -> dict:
	"""The session user's open ToDos, for either To Do widget.

	`count` is the true total and may exceed `len(todos)`; the widgets put it on
	the badge and use `truncated` to decide whether to nudge the reader to the
	full list.
	"""
	if sort_by not in SORT_TYPES:
		sort_by = DEFAULT_SORT

	limit = max(1, min(cint(limit) or MAX_ROWS, MAX_ROWS))
	current_date = getdate(today())

	todos = []
	for filters in _mine_filter_sets():
		todos += frappe.get_list(
			"ToDo",
			filters=filters,
			fields=LIST_FIELDS,
			# a cap per arm keeps a pathological backlog out of memory; `count`
			# still reports the real total
			limit_page_length=MAX_ROWS,
			order_by="modified desc",
		)

	key, reverse = _sorter(sort_by)
	todos.sort(key=key, reverse=reverse)

	for todo in todos:
		todo.title = _as_title(todo.description)
		todo.overdue = bool(todo.date) and getdate(todo.date) < current_date
		# the raw HTML was only needed to derive the title
		del todo.description

	count = get_open_todo_count()

	return {
		"todos": todos[:limit],
		"count": count,
		"sort_by": sort_by,
		"truncated": count > len(todos[:limit]),
	}


@frappe.whitelist(methods=["POST"])
def close_todo(name: str) -> dict:
	"""Close one ToDo and return the user's updated open count.

	Through the document rather than `db_set`, so the assignment-completed
	comment and the `_assign` refresh on the referenced document still happen,
	exactly as they would when closing from the ToDo form.

	POST only: `@frappe.whitelist()` would answer a GET as well, and Frappe
	checks its CSRF token only on requests with a body.
	"""
	todo = frappe.get_doc("ToDo", name)
	todo.check_permission("write")

	if todo.status != "Closed":
		todo.status = "Closed"
		todo.save()

	return {"name": todo.name, "count": get_open_todo_count()}
