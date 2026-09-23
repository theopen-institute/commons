"""What a query with derived fields costs, asked of MariaDB rather than guessed.

The advice in the module notes comes down to one question -- does this query
look up a page of rows, or every row? -- and EXPLAIN answers it. `explain`
builds the query exactly as a list would (the same engine, this user's
permissions), and returns its SQL, MariaDB's plan, and the plan read back in
the module notes' terms.

From a console, or from the command line::

	bench --site SITE execute commons.derived_docfields.diagnostics.explain \\
		--kwargs '{"doctype": "Faculty", "fields": ["name", "custom_first_name"], "order_by": "custom_first_name asc"}'

`analyze=True` runs the query too (ANALYZE), which adds the rows MariaDB
actually read to each step. It is still only a SELECT.
"""

import frappe

from commons.derived_docfields import install


def explain(
	doctype: str,
	fields: list | None = None,
	filters: dict | list | None = None,
	order_by: str | None = None,
	group_by: str | None = None,
	limit: int = 20,
	analyze: bool = False,
) -> dict:
	"""The SQL a list of `doctype` builds for these arguments, MariaDB's plan, and what it means."""
	install()
	query = frappe.get_list(
		doctype,
		fields=fields or ["name"],
		filters=filters,
		order_by=order_by,
		group_by=group_by,
		limit=limit,
		run=False,
	)
	sql, params = query.walk()
	plan = frappe.db.sql(("ANALYZE " if analyze else "EXPLAIN ") + sql, params, as_dict=True)
	return {"sql": query.get_sql(), "plan": plan, "notes": read_plan(plan, f"tab{doctype}")}


def read_plan(plan: list[dict], host_table: str) -> list[str]:
	"""The plan's rows in the module notes' terms. Only what is worth knowing; nothing when all is well."""
	notes = []
	for step in plan:
		table = step.get("table") or ""
		extra = step.get("Extra") or ""
		rows = step.get("r_rows") or step.get("rows")
		name = "the host table" if table == host_table else table

		if step.get("type") == "ALL":
			notes.append(f"Reads all of {name} (about {rows} rows): nothing narrows it before the join.")
		if "filesort" in extra:
			notes.append(
				f"Sorts every matching row of {name} before taking a page: fine on a small table, "
				"slow on a large one if the sort is on a derived field."
			)
		if "temporary" in extra:
			notes.append(f"Builds a temporary table from {name}: grouping or sorting on a derived field.")
		if table != host_table and step.get("type") not in ("eq_ref", "const", "system", "ref", None):
			notes.append(
				f"Joins {name} without a primary-key lookup ({step.get('type')}): check the path's link fields."
			)
	return notes
