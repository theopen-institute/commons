"""Derived docfields: a field whose value is read through a link, by a real join.

A derived field is a Custom Field with `derived_from = "link_field.target_field"`,
the syntax of Fetch From. Nothing is stored. Every read joins to the linked
record, so a Member's phone shows on every Faculty the moment it changes, and
switching the feature off loses nothing. The target can itself be derived, which
is how a value is reached through several links, and the first link can be a
Dynamic Link given `derived_from_doctypes`, the doctypes it may point at.

Switched on by "Enable Derived Docfields" in Commons Settings, and read on every
query: off, every query is exactly core's.

Where the pieces are
--------------------
* `registry` -- which fields are derived (cached), and the path each takes.
* `validation` -- the checks when a field is defined, which are also the only
  permission checks against the doctypes a path passes through.
* `engine` -- the query half. `install` below swaps it in for core's engine,
  and teaches Customize Form the three properties (`extend_customize_form`).
* `document` -- the single-record half: forms, both REST APIs, print, and server
  code reading `doc.field`. `install` puts it in first.
* `api` -- what a form asks when one of its links changes.
* `diagnostics` -- `explain`, for what a query with derived fields will cost.

Permissions
-----------
Checked when a field is *defined*, not when it is read. Whoever defines it must
be able to read every doctype and field along its path; after that the field
belongs to the host doctype, and the host's own rules decide who sees it -- its
row permissions and the derived field's permlevel. A reader who cannot open the
linked Member still sees the phone on the Faculty they can open. Anyone who can
edit the link can therefore see any Member's phone by pointing the link at them:
the derived field's permlevel is the control for that.

Performance, and how to design for it
-------------------------------------
Each step along a path is a primary-key lookup in the linked table. What costs
is how many host rows need one: a page's worth, or all of them.

1. Show freely. A derived column in a list or report costs one lookup per shown
   row per step, whatever the size of the table.
2. Index the host's link field (Search Index) if people filter by the derived
   field with equality, and index the source field too. MariaDB can then start
   from the source's index and find the few matching host rows; without it, it
   reads every host row. Link fields are not indexed by default.
3. Store what large lists sort by. Sorting by a derived field reads every
   matching host row and sorts them. On a doctype past roughly 100,000 rows, a
   column that is the default sort or a standing filter wants to be stored
   (Fetch From, or a real field).
4. Prefer equality to `like '%...%'` on large tables: a leading wildcard can't
   use any index.
5. Keep paths short -- two or three steps. Each adds a lookup per row touched.
6. Keep Dynamic Link candidate lists short. Each candidate is another join.
7. Include in Wildcard Queries only on doctypes nobody reads in bulk with `*`.
   Every such query, unlimited ones in background jobs included, pays the joins.
8. Derived fields on child tables are fine: a document's rows are looked up
   together, one query per linked doctype for the whole table.
9. When unsure, ask MariaDB: `diagnostics.explain` builds the query a list
   would, and returns its SQL, its plan, and the plan read back in these terms.

The definition check says the most important of these as warnings, when a field
is saved in a way that would make them bite.
"""

import inspect

import frappe

# The engine methods `engine.DerivedEngine` overrides or calls, as core spells
# them today. If an upgrade changes any of them the swap stands down rather than
# guess -- the feature then reads as switched off -- and says why, once.
EXPECTED_ENGINE = {
	"get_query": None,
	"_parse_single_field_item": ("self", "field"),
	"parse_fields": ("self", "fields"),
	"apply_field_permissions": ("self",),
	"_validate_and_prepare_filter_field": ("self", "field", "doctype"),
	"_validate_and_parse_field_for_clause": ("self", "field_name", "clause_name"),
	"_apply_default_order_by": ("self",),
	"build_filter_conditions": ("self", "filters", "conditions", "ignore_permissions"),
	"get_permission_type": ("self", "doctype", "parent_doctype"),
}

# Why the engine was not installed in this process, once found.
_refused: str | None = None


def install() -> None:
	"""Put `engine.DerivedEngine` where core looks for its query engine.

	Every query builder in core -- `frappe.qb.get_query`, and through it
	`get_list`, `get_all`, `db.get_value`, reportview and the REST API -- looks
	`frappe.database.query.Engine` up when it runs, so replacing that one name
	reaches them all. Process-wide and idempotent: a worker serves every site on
	the bench, so whether a query uses derived fields is decided per query, from
	that site's switch, not here.

	Called from `before_request` and `before_job`, which covers the web and the
	workers. A console session or a test calls it itself.
	"""
	global _refused

	from frappe.database import query as core_query

	if getattr(core_query.Engine, "_commons_derived", False) or _refused:
		return

	extend_customize_form()
	# First, and whatever becomes of the engine: without a derived controller,
	# core evaluates a virtual field's `options` as Python, and a derived Link's
	# options are a doctype's name -- its records would fail to load.
	install_documents()

	if problems := incompatibilities(core_query.Engine):
		_refused = "; ".join(problems)
		frappe.logger("commons").warning(f"Derived docfields not installed: {_refused}")
		return

	try:
		from commons.derived_docfields.engine import DerivedEngine
	except Exception as e:
		_refused = f"engine failed to import: {e!r}"
		frappe.logger("commons").warning(f"Derived docfields not installed: {_refused}")
		return

	core_query.Engine = DerivedEngine


def install_documents() -> None:
	"""The document half (`commons.derived_docfields.document`), logged if it can't go in."""
	try:
		from commons.derived_docfields.document import install as install_document_controllers

		install_document_controllers()
	except Exception as e:
		frappe.logger("commons").warning(f"Derived docfields: document controllers not installed: {e!r}")


def extend_customize_form() -> None:
	"""Let Customize Form carry the three derived properties to and from a Custom Field.

	Customize Form copies a field's properties through one module-level table,
	`docfield_properties`, read on every load and save: into its grid from
	meta, from its grid into the Custom Fields it creates and updates, and into
	Property Setters for standard fields. Adding three entries is all it takes.
	For a standard field all three are always empty on both sides, so no
	Property Setter is ever written for them -- and the fixtures hide them there
	anyway, since a standard field has a column and can't be derived.
	"""
	from commons.derived_docfields.registry import CANDIDATES, DERIVED_FROM, IN_WILDCARD

	try:
		from frappe.custom.doctype.customize_form.customize_form import docfield_properties
	except ImportError:
		return
	docfield_properties.setdefault(DERIVED_FROM, "Data")
	docfield_properties.setdefault(CANDIDATES, "Small Text")
	docfield_properties.setdefault(IN_WILDCARD, "Check")


def incompatibilities(engine_class) -> list[str]:
	"""What about core's engine no longer matches what `DerivedEngine` was written against."""
	problems = []
	for name, parameters in EXPECTED_ENGINE.items():
		method = getattr(engine_class, name, None)
		if not callable(method):
			problems.append(f"Engine.{name} is gone")
			continue
		if parameters is not None and tuple(inspect.signature(method).parameters) != parameters:
			problems.append(f"Engine.{name} now takes {tuple(inspect.signature(method).parameters)}")
	return problems
