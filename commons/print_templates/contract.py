"""A Web Template's inputs, declared in its Fields table.

Each row is one parameter a caller passes, by name:

    {{ render_web_template("Student Statement", student=doc.name) }}

-- its fieldname, its fieldtype, and whether it is required. The Context Prep
turns the inputs into whatever the layout reads, so the inputs are the whole of
what a Print Format has to know about the template. For Student Statement that
is one Link to Student; everything on the page is looked up from it.

The table is read the way Frappe's own values editor reads it
(`frappe/public/js/frappe/utils/web_template.js`): rows before the first Table
Break are single inputs, and a Table Break starts a list input whose rows have
the fields after it, up to the next Table Break. Section and Column Breaks are
layout for the form and declare nothing.

Nothing here stops a print. A real print is not checked at all, since a
statement is better printed short than not printed; the Test PDF dialog is
where a mismatch is reported, as warnings beside the PDF.
"""

import datetime

import frappe
from frappe import _

LAYOUT = {"Section Break", "Column Break"}
TEXT = {"Data", "Small Text", "Text", "Markdown Editor", "Select", "Link", "Attach Image"}
NUMBER = {"Float", "Currency"}


def _rows(fields) -> list[dict]:
	rows = []
	for f in fields or []:
		# Child rows when the template is being saved, dicts from the test dialog.
		# (Not `hasattr(f, "as_dict")`: a frappe._dict answers every attribute, with None.)
		f = frappe._dict(f if isinstance(f, dict) else f.as_dict())
		f.fieldname = f.fieldname or frappe.scrub(f.label or "")
		if f.fieldname or f.fieldtype in LAYOUT:
			rows.append(f)
	return rows


def declared(fields) -> tuple[list, list]:
	"""Single inputs, and `(table_break, [its row fields])` for each list input."""
	top, tables = [], []
	for f in _rows(fields):
		if f.fieldtype == "Table Break":
			tables.append((f, []))
		elif f.fieldtype in LAYOUT:
			continue
		elif tables:
			tables[-1][1].append(f)
		else:
			top.append(f)
	return top, tables


def has_inputs(fields) -> bool:
	top, tables = declared(fields)
	return bool(top or tables)


def check(fields, inputs: dict) -> list[str]:
	"""What in `inputs` does not match the declared fields; empty when nothing is declared."""
	top, tables = declared(fields)
	if not top and not tables:
		return []

	warnings = []
	for f in top:
		warnings += _check_one(f, inputs, f.fieldname)
	for table, row_fields in tables:
		warnings += _check_one(table, inputs, table.fieldname)
		rows = inputs.get(table.fieldname)
		if isinstance(rows, list):
			for i, row in enumerate(rows):
				path = f"{table.fieldname}[{i}]"
				if not isinstance(row, dict):
					warnings.append(_("{0} should be an object, one key per column.").format(path))
					continue
				for f in row_fields:
					warnings += _check_one(f, row, f"{path}.{f.fieldname}")

	known = {f.fieldname for f in top} | {t.fieldname for t, _row in tables}
	for key in inputs:
		if key not in known:
			warnings.append(_("{0} is passed but not declared in Fields.").format(key))
	return warnings


def _check_one(f, values: dict, path: str) -> list[str]:
	if f.fieldname not in values or values[f.fieldname] in (None, ""):
		return [_("{0} is required but missing.").format(path)] if f.reqd else []
	value = values[f.fieldname]
	expected = _expected(f, value)
	if expected:
		return [_("{0} should be {1}, not {2}.").format(path, expected, _describe(value))]
	if f.fieldtype == "Select" and f.options:
		options = [o for o in f.options.split("\n") if o]
		if options and value not in options:
			return [_("{0} is {1}, which is not one of its options.").format(path, frappe.as_json(value))]
	if f.fieldtype == "Link" and f.options and not frappe.db.exists(f.options, value):
		return [_("{0}: there is no {1} named {2}.").format(path, _(f.options), frappe.as_json(value))]
	return []


def _expected(f, value) -> str | None:
	"""What `value` should have been, or None when it is the declared type."""
	kind = f.fieldtype
	if kind == "Table Break":
		return None if isinstance(value, list) else _("a list")
	if kind in TEXT:
		return None if isinstance(value, str) else _("text")
	if kind == "Int":
		return None if isinstance(value, int) and not isinstance(value, bool) else _("a whole number")
	if kind in NUMBER:
		return None if isinstance(value, int | float) and not isinstance(value, bool) else _("a number")
	if kind == "Check":
		return None if value in (0, 1) else _("0 or 1")
	if kind == "Date":
		if isinstance(value, datetime.date):
			return None
		try:
			datetime.date.fromisoformat(str(value)[:10])
			return None
		except ValueError:
			return _("a date (YYYY-MM-DD)")
	if kind == "JSON":
		return None if isinstance(value, dict | list) else _("an object or a list")
	return None


def _describe(value) -> str:
	if isinstance(value, bool):
		return _("true/false")
	if isinstance(value, str):
		return _("text")
	if isinstance(value, int | float):
		return _("a number")
	if isinstance(value, list):
		return _("a list")
	if isinstance(value, dict):
		return _("an object")
	return type(value).__name__


def validate_fields(fields) -> None:
	"""On save: a Link input has to say what it links to, or it cannot be checked or picked."""
	top, tables = declared(fields)
	for f in top + [f for _t, rows in tables for f in rows]:
		if f.fieldtype == "Link" and not (f.options and frappe.db.exists("DocType", f.options)):
			frappe.throw(
				_("Input {0} is a Link, so its Options must name a DocType.").format(
					frappe.bold(f.fieldname)
				),
				title=_("Fields"),
			)
