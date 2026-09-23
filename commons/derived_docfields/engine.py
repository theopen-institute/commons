"""The query half: a derived fieldname becomes a join wherever a query names it.

`DerivedEngine` is core's `frappe.database.query.Engine` with four places taught
about derived fields -- the four where the engine turns a name into a column:

* `_parse_single_field_item`, for the select list;
* `_validate_and_prepare_filter_field`, for filters and or-filters;
* `_validate_and_parse_field_for_clause`, for order by and group by;
* `_apply_default_order_by`, for a doctype whose own sort field is derived.

Each hands a derived name to `derived_term`, which walks the field's plan
(`registry.plan`) and returns something pypika can put where a column would go:
the target column on an aliased `LEFT JOIN`, or a `COALESCE` over one join per
candidate for a Dynamic Link. Everything else -- operators, null handling, date
conversion, masking, pagination, counts -- is core's, unchanged, because by the
time core sees the term it looks like any other column.

The joins
---------
One `LEFT JOIN` per step of a path, named after the path (`dd_member`,
`dd_instructor__member`), so two links to the same doctype get two joins and
two derived fields that share a path share its join. A left join on the target's
primary key never multiplies rows, so a join a query does not end up needing
costs a lookup and changes nothing. The target doctype's permissions are not
applied: a derived field is part of the host doctype, and who may read it was
settled when it was defined (see `commons.derived_docfields.validation`). Only
the host's own rules apply -- its row conditions, which core adds as usual, and
the derived field's permlevel, checked here.

Where there is nothing to join to, the same walk produces correlated subqueries
instead (`inline`): in `build_filter_conditions`, whose output is spliced into
somebody else's raw SQL, and in UPDATE and DELETE queries, which cannot take a
join.

Everything here is opt-in per query: a doctype with no derived fields, or a site
with the switch off, gets exactly core's query. `registry.active_for` answers
that first, and every override below returns straight to core when it says so.
"""

import re
import zlib
from functools import cached_property

import frappe
from frappe import _
from frappe.database import query as core_query
from frappe.database.query import DynamicTableField
from frappe.database.utils import get_doctype_sort_info
from frappe.query_builder import functions
from pypika.enums import Order
from pypika.terms import NullValue, Star, Term
from pypika.utils import format_alias_sql

from commons.derived_docfields import registry
from commons.derived_docfields.registry import BrokenPath, Column

# Core's own `Engine`, even if this module is imported again after `install`
# has already swapped it out.
Engine = getattr(core_query.Engine, "_commons_base", core_query.Engine)

# A field as the engine's callers write it: `phone`, `` `phone` ``,
# `tabFaculty.phone`, `` `tabFaculty`.`phone` ``. Core's `FIELD_PARSE_REGEX`,
# kept here rather than imported so that core renaming it breaks nothing.
FIELD = re.compile(r"^(?:(`?)(tab[\w\s-]+)\1\.)?(`?)(\w+)\3$")
ALIAS = re.compile(r"\s+as\s+", flags=re.IGNORECASE)

# MariaDB allows identifiers up to 64 characters.
MAX_ALIAS = 64


class DerivedField(DynamicTableField):
	"""A derived field in a select list, answering under its own fieldname."""

	def __init__(self, doctype: str, fieldname: str, alias: str | None = None) -> None:
		super().__init__(doctype, fieldname, doctype, alias=alias or fieldname)

	def apply_select(self, query, engine=None):
		term = engine.derived_term(self.fieldname)
		return engine.query.select(term.as_(self.alias))

	def apply_join(self, query, engine=None):
		engine.derived_term(self.fieldname)
		return engine.query


class Scalar(Term):
	"""A one-value subquery that can stand where a column does.

	pypika's `QueryBuilder` is a `Term`, but it overrides `==` to compare two
	*queries*, so `subquery == "x"` is Python's `False` -- which core's filter
	code then drops without a word. A `DELETE` filtered on a derived field
	would delete every row. This wraps the subquery so comparisons build SQL.
	"""

	def __init__(self, query, alias: str | None = None) -> None:
		super().__init__(alias=alias)
		self.query = query

	def nodes_(self):
		yield self
		yield from self.query.nodes_()

	def get_sql(self, **kwargs) -> str:
		with_alias = kwargs.pop("with_alias", False)
		kwargs.pop("subquery", None)
		sql = self.query.get_sql(subquery=True, **kwargs)
		return format_alias_sql(sql, self.alias if with_alias else None, **kwargs)


class DerivedEngine(Engine):
	_commons_derived = True
	_commons_base = Engine

	def get_query(self, table, *args, **kwargs):
		# Per query, not per instance: core reuses an engine now and then.
		self.__dict__.pop("derived", None)
		self._derived_joins = {}
		# UPDATE, INSERT and DELETE can't take a join; see the module docstring.
		self._derived_inline = bool(kwargs.get("update") or kwargs.get("into") or kwargs.get("delete"))
		return super().get_query(table, *args, **kwargs)

	@cached_property
	def derived(self) -> dict[str, registry.Definition]:
		"""The derived fields this query should honour: none at all, almost always."""
		return registry.active_for(getattr(self, "doctype", None))

	# Naming
	# ------

	def derived_name(self, field) -> str | None:
		"""The derived fieldname `field` refers to on this query's doctype, if it does."""
		if not isinstance(field, str) or not self.derived:
			return None
		match = FIELD.match(field.strip())
		if not match:
			return None
		table, name = match.group(2), match.group(4)
		if table and table[3:] != self.doctype:
			return None
		return name if name in self.derived else None

	def derived_term(self, fieldname: str):
		"""What to put where `fieldname`'s column would go: a join's column, or NULL.

		NULL for a path that no longer resolves, reported once, rather than a
		failed query: one broken field should not take a whole list down with it.
		"""
		try:
			node = registry.plan(self.doctype, fieldname)
		except BrokenPath as e:
			report_broken(self.doctype, fieldname, e)
			return NullValue()
		return self._term(node, self.table, (), inline=getattr(self, "_derived_inline", False))

	def _term(self, node, table, path: tuple, inline: bool):
		if isinstance(node, Column):
			return table[node.fieldname]

		link = self._term(node.link, table, path, inline)
		kind = self._term(node.type_field, table, path, inline) if node.type_field else None
		step = (*path, node.definition.link_field)

		values = []
		for target, target_node in node.targets:
			hop = step if kind is None else (*step, target)
			joined = frappe.qb.DocType(target).as_(alias(hop))
			condition = joined.name == link
			if kind is not None:
				condition = (kind == target) & condition

			if inline:
				value = self._term(target_node, joined, hop, inline=True)
				values.append(Scalar(frappe.qb.from_(joined).select(value).where(condition).limit(1)))
				continue

			if hop not in self._derived_joins:
				self.query = self.query.left_join(joined).on(condition)
				self._derived_joins[hop] = joined
			values.append(self._term(target_node, self._derived_joins[hop], hop, inline=False))

		return values[0] if len(values) == 1 else functions.Coalesce(*values)

	# Select
	# ------

	def _parse_single_field_item(self, field):
		if isinstance(field, str) and self.derived:
			# `phone as p`, split the way core splits it: the last alias wins.
			name_part, alias_part = field, None
			parts = ALIAS.split(field)
			if len(parts) > 1:
				name_part, alias_part = parts[0].strip(), parts[-1].strip().strip("`\"'")
			if (name := self.derived_name(name_part)) is not None:
				return DerivedField(self.doctype, name, alias_part)
		return super()._parse_single_field_item(field)

	def parse_fields(self, fields):
		"""Core's parse, plus the fields opted into `*` wherever `*` was asked for."""
		parsed = super().parse_fields(fields)
		if self.derived and any(isinstance(field, Star) for field in parsed):
			named = {field.fieldname for field in parsed if isinstance(field, DerivedField)}
			parsed.extend(
				DerivedField(self.doctype, fieldname)
				for fieldname, definition in self.derived.items()
				if definition.in_wildcard and fieldname not in named
			)
		return parsed

	def apply_field_permissions(self):
		"""Core's field permissions, with derived fields judged by their own permlevel.

		Core would drop every derived field: it is virtual, and core's permitted
		set leaves virtual fields out. So the derived ones are judged here and
		everything between them is handed to core in runs, which keeps the
		select list in the order it was asked for -- `as_list` callers read
		results by position.
		"""
		fields = self.fields
		if not any(isinstance(field, DerivedField) for field in fields):
			return super().apply_field_permissions()

		permitted = self._permitted_derived(for_filtering=False)
		allowed, run = [], []

		def flush():
			if run:
				self.fields = list(run)
				allowed.extend(super(DerivedEngine, self).apply_field_permissions())
				run.clear()

		for field in fields:
			if isinstance(field, DerivedField):
				flush()
				if field.fieldname in permitted:
					allowed.append(field)
			else:
				run.append(field)
		flush()
		self.fields = fields
		return allowed

	# Filters, order by, group by
	# ---------------------------

	def _validate_and_prepare_filter_field(self, field, doctype=None):
		if (doctype is None or doctype == self.doctype) and (name := self.derived_name(field)) is not None:
			self._check_derived_permission(name)
			return self.derived_term(name)
		return super()._validate_and_prepare_filter_field(field, doctype)

	def _validate_and_parse_field_for_clause(self, field_name, clause_name):
		# An alias from the select list is core's to resolve, and resolves to
		# the same value: a derived field is selected under its own name.
		if (
			field_name not in self.function_aliases
			and field_name not in self.field_aliases
			and (name := self.derived_name(field_name)) is not None
		):
			self._check_derived_permission(name)
			return self.derived_term(name)
		return super()._validate_and_parse_field_for_clause(field_name, clause_name)

	def _apply_default_order_by(self):
		"""Core's default sort, for a doctype whose configured sort field is derived.

		Rare, and slow on a large table (see the module notes), but core's own
		version would address a column that isn't there.
		"""
		if not self.derived:
			return super()._apply_default_order_by()

		sort_field, sort_order = get_doctype_sort_info(self.doctype)
		specs = []
		for spec in sort_field.split(","):
			if parts := spec.strip().split(maxsplit=1):
				specs.append((parts[0], parts[1].lower() if len(parts) > 1 else sort_order.lower()))
		if not any(field_name in self.derived for field_name, _order in specs):
			return super()._apply_default_order_by()

		for field_name, spec_order in specs:
			field = self.derived_term(field_name) if field_name in self.derived else self.table[field_name]
			if self.db_query_compat:
				direction = Order.desc if spec_order == "desc" else Order.asc
			else:
				direction = Order.asc if spec_order == "asc" else Order.desc
			self.query = self.query.orderby(field, order=direction)

	def build_filter_conditions(self, filters, conditions, ignore_permissions=None):
		"""Core's, with derived fields written as subqueries: the output has no joins to lean on."""
		self._derived_inline = True
		try:
			return super().build_filter_conditions(filters, conditions, ignore_permissions)
		finally:
			self._derived_inline = False

	# Permissions
	# -----------

	def _check_derived_permission(self, fieldname: str) -> None:
		if self.apply_permissions and fieldname not in self._permitted_derived(for_filtering=True):
			frappe.throw(
				_("You do not have permission to access field: {0}").format(
					frappe.bold(f"{self.doctype}.{fieldname}")
				),
				frappe.PermissionError,
				title=_("Permission Error"),
			)

	def _permitted_derived(self, for_filtering: bool) -> set[str]:
		"""The derived fields this user may see, by the host doctype's permlevels.

		The same rules core applies to stored fields, restated because core's
		version skips virtual ones: read access by permlevel, the search fields
		for a user with only select, and -- for filtering and sorting only --
		every permlevel-0 field for such a user, as `_get_filterable_fields` allows.
		"""
		if not self.apply_permissions:
			return set(self.derived)

		key = ("commons_derived", for_filtering)
		cache = self.permitted_fields_cache
		if key in cache:
			return cache[key]

		meta = frappe.get_meta(self.doctype)
		names = set(self.derived)
		if not meta.get_permissions(parenttype=self.parent_doctype):
			permitted = names
		else:
			permission_type = self.get_permission_type(self.doctype, self.parent_doctype)
			if for_filtering and permission_type == "select":
				permitted = (
					set()
					if meta.istable
					else {name for name in names if not (meta.get_field(name).permlevel or 0)}
				)
			else:
				permitted = names & set(
					meta.get_permitted_fieldnames(
						parenttype=self.parent_doctype,
						user=self.user,
						permission_type=permission_type,
						with_virtual_fields=True,
					)
				)
		cache[key] = permitted
		return permitted


def alias(path: tuple) -> str:
	"""A join's name, from the link fields (and Dynamic Link candidates) it took to get there.

	Readable where it fits, because it is what EXPLAIN shows; hashed when it
	does not, since MariaDB stops at 64 characters.
	"""
	readable = "dd_" + "__".join(frappe.scrub(part) for part in path)
	if len(readable) <= MAX_ALIAS:
		return readable
	return f"{readable[: MAX_ALIAS - 10]}_{zlib.crc32(readable.encode()):08x}"


# Broken paths already reported by this process, so a list view doesn't write
# an Error Log per request.
_reported: set[tuple] = set()


def report_broken(doctype: str, fieldname: str, error: Exception) -> None:
	key = (getattr(frappe.local, "site", None), doctype, fieldname)
	if key in _reported:
		return
	_reported.add(key)
	frappe.log_error(
		title=f"Derived field {doctype}.{fieldname} does not resolve",
		message=f"{error}\n\nIt reads as empty until its Derived From is fixed.",
	)
