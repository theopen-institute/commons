"""Which fields are derived, and the path each one takes to its value.

Two layers, kept apart because they change at different speeds.

`definitions` is what the site has declared: every Custom Field with a
`derived_from`, read in one query and kept in `frappe.client_cache` -- the
process-local cache core uses for hooks and schema, invalidated through redis.
It is asked on every query the engine builds, so it has to answer without a
round trip; a Custom Field save or delete drops it (`clear`), and so does a full
`bench clear-cache`.

`plan` is how one of those fields reaches its value *today*, worked out from
current meta: which link it follows, into which doctype (or doctypes, for a
Dynamic Link), and whether what it finds there is a column or another derived
field to follow in turn. It is worked out afresh each time rather than cached
with the definitions, because it depends on every doctype along the way -- a
field renamed three hops out changes the plan without touching any Custom Field
here.

A plan is a small tree of `Column` and `Hop` nodes, and three readers walk it:
`commons.derived_docfields.engine` turns it into joins, `.validation` checks it
when someone defines a field, and the document layer resolves it for a single
record. A path that no longer resolves raises `BrokenPath`, and each reader
decides what that means for it: the validation refuses, the engine selects NULL.
"""

from dataclasses import dataclass

import frappe
from frappe.database.query import CORE_DOCTYPES
from frappe.model import child_table_fields, default_fields, no_value_fields, table_fields

from commons.commons_core import settings

CACHE_KEY = "commons_derived_docfields"

# The Custom Field properties this module adds, all three on both Custom Field
# and Customize Form Field (see `commons/fixtures/README.md`).
DERIVED_FROM = "derived_from"
CANDIDATES = "derived_from_doctypes"
IN_WILDCARD = "derived_in_wildcard"
PROPERTIES = (DERIVED_FROM, CANDIDATES, IN_WILDCARD)

# Doctypes the engine never asks about: core's own `CORE_DOCTYPES`, whose meta
# the query engine itself refuses to load mid-query. It also has to include
# Custom Field and Singles, because reading the definitions is a query on the
# one and reading the switch a query on the other -- asking about either would
# recurse. None of them can carry a derived field.
_NEVER = CORE_DOCTYPES | {"Custom Field", "Singles"}

# Standard fields every table has, which a path may end on. `doctype` is in
# core's `default_fields` but is not a column.
_STANDARD = frozenset(default_fields) - {"doctype"}


class BrokenPath(frappe.ValidationError):
	"""A derived field whose path no longer leads anywhere."""


@dataclass(frozen=True)
class Definition:
	"""One derived field as its Custom Field declares it."""

	doctype: str
	fieldname: str
	link_field: str
	target_field: str
	# The doctypes a Dynamic Link may point at, in the order they were listed.
	# Empty for a plain Link, whose target comes from the link field's options.
	candidates: tuple[str, ...]
	in_wildcard: bool


@dataclass(frozen=True)
class Column:
	"""Where a path ends: a real column (or standard field) on `doctype`."""

	doctype: str
	fieldname: str


@dataclass(frozen=True)
class Hop:
	"""One step along a path: follow `link` on `doctype` into each target.

	`link` and `type_field` are themselves nodes, because the link being
	followed may be a derived field too -- a derived Link can be followed like
	a stored one. `targets` pairs each target doctype with the node for the
	target field on it: one pair for a Link, one per candidate for a Dynamic
	Link, where `type_field` reads which of them a row points at.
	"""

	doctype: str
	definition: Definition
	link: "Node"
	type_field: "Node | None"
	targets: tuple[tuple[str, "Node"], ...]


Node = Column | Hop


def parse_candidates(value: str | None) -> tuple[str, ...]:
	"""The doctypes listed in `derived_from_doctypes`: one per line, in order, once each."""
	seen = []
	for line in (value or "").splitlines():
		if (name := line.strip()) and name not in seen:
			seen.append(name)
	return tuple(seen)


def parse(doctype: str, fieldname: str, derived_from: str | None, candidates=None, in_wildcard=0):
	"""A `Definition`, or None if `derived_from` is not `link_field.target_field`."""
	link_field, dot, target_field = (derived_from or "").strip().partition(".")
	if not (dot and link_field.isidentifier() and target_field.isidentifier()):
		return None
	return Definition(
		doctype=doctype,
		fieldname=fieldname,
		link_field=link_field,
		target_field=target_field,
		candidates=parse_candidates(candidates),
		in_wildcard=bool(in_wildcard),
	)


def definitions() -> dict[str, dict[str, Definition]]:
	"""Every derived field on the site, by doctype and then by fieldname.

	Answers `{}` between this app arriving on a site and the migrate that adds
	the `derived_from` column, which is also when nothing can have declared one.
	"""
	return frappe.client_cache.get_value(CACHE_KEY, generator=_load)


def _load() -> dict[str, dict[str, Definition]]:
	"""Read the definitions in raw SQL, beneath the engine that is asking for them.

	Through `frappe.get_all` this would recurse whenever a meta cache is cold:
	loading Custom Field's meta queries Custom DocPerm, that query asks the
	engine which fields are derived, and the engine asks here again.
	"""
	found: dict[str, dict[str, Definition]] = {}
	if not frappe.db.has_column("Custom Field", DERIVED_FROM):
		return found

	rows = frappe.db.sql(
		"""select dt, fieldname, derived_from, derived_from_doctypes, derived_in_wildcard
		from `tabCustom Field`
		where ifnull(derived_from, '') != ''
		order by dt asc, idx asc""",
		as_dict=True,
	)
	for row in rows:
		if definition := parse(
			row.dt, row.fieldname, row.derived_from, row.derived_from_doctypes, row.derived_in_wildcard
		):
			found.setdefault(row.dt, {})[row.fieldname] = definition
	return found


def clear(*args, **kwargs) -> None:
	"""Forget the definitions: now, and again once this transaction ends either way.

	A doc event on Custom Field, so it takes the hook's arguments. Now, so the
	rest of this request sees the change. Again at the end, because anything
	that reads the definitions in between -- in this process, from the
	uncommitted row, or in another, from the old committed one -- puts a copy
	back that is right for only one of the two outcomes.
	"""
	frappe.client_cache.delete_value(CACHE_KEY)
	if db := getattr(frappe.local, "db", None):
		db.after_commit.add(_forget)
		db.after_rollback.add(_forget)


def _forget() -> None:
	frappe.client_cache.delete_value(CACHE_KEY)


def enabled() -> bool:
	return settings.feature_enabled(settings.ENABLE_DERIVED_DOCFIELDS)


def active_for(doctype: str) -> dict[str, Definition]:
	"""The derived fields a query on `doctype` should honour: none while switched off.

	The engine calls this for every query it builds, so it is ordered cheapest
	first: a doctype that can't carry derived fields, then one that has none
	(nearly every doctype, answered from the process-local cache), and only then
	the switch.
	"""
	if not doctype or doctype in _NEVER or getattr(frappe.local, "commons_derived_asking", False):
		return {}
	found = definitions().get(doctype)
	if not found:
		return {}
	# Reading the switch loads a document, and a cold load runs queries of its
	# own; none of those can be about derived fields, and asking would recurse.
	frappe.local.commons_derived_asking = True
	try:
		on = enabled()
	finally:
		frappe.local.commons_derived_asking = False
	return found if on else {}


def plan(doctype: str, fieldname: str, overlay: Definition | None = None) -> Node:
	"""How `fieldname` on `doctype` reaches its value, from today's meta.

	Not cached: it is a handful of lookups in meta core already holds, and a
	cached plan would outlive a field renamed further along its path -- in a
	console session or a long job there is no request boundary to drop it at.
	Raises `BrokenPath` naming the first step that no longer resolves.

	`overlay` is a definition not saved yet, planned as though it were: the
	validation checks a field before it lands, including whether it would
	close a loop through fields already there.
	"""
	return _plan(doctype, fieldname, frozenset(), overlay)


def _plan(doctype: str, fieldname: str, seen: frozenset, overlay: Definition | None = None) -> Node:
	if overlay is not None and (overlay.doctype, overlay.fieldname) == (doctype, fieldname):
		definition = overlay
	else:
		definition = definitions().get(doctype, {}).get(fieldname)
	if definition is None:
		return _column(doctype, fieldname)

	if (doctype, fieldname) in seen:
		raise BrokenPath(f"{doctype}.{fieldname} derives from itself")
	seen = seen | {(doctype, fieldname)}

	meta = _meta(doctype)
	link_df = meta.get_field(definition.link_field)
	if link_df is None:
		raise BrokenPath(f"{doctype} has no field {definition.link_field}")

	link = _plan(doctype, definition.link_field, seen, overlay)

	if link_df.fieldtype == "Link":
		if definition.candidates:
			raise BrokenPath(
				f"{doctype}.{definition.link_field} is a Link, so Derived From DocTypes must be empty"
			)
		target = _joinable(link_df.options, via=f"{doctype}.{definition.link_field}")
		return Hop(
			doctype=doctype,
			definition=definition,
			link=link,
			type_field=None,
			targets=((target, _plan(target, definition.target_field, seen, overlay)),),
		)

	if link_df.fieldtype == "Dynamic Link":
		if not definition.candidates:
			raise BrokenPath(
				f"{doctype}.{definition.link_field} is a Dynamic Link, so Derived From DocTypes must list "
				"the doctypes it may point at"
			)
		via = f"{doctype}.{definition.link_field}"
		return Hop(
			doctype=doctype,
			definition=definition,
			link=link,
			type_field=_plan(doctype, link_df.options, seen, overlay),
			targets=tuple(
				(target, _plan(target, definition.target_field, seen, overlay))
				for target in (_joinable(candidate, via=via) for candidate in definition.candidates)
			),
		)

	raise BrokenPath(
		f"{doctype}.{definition.link_field} is a {link_df.fieldtype}, not a Link or Dynamic Link"
	)


def _column(doctype: str, fieldname: str) -> Column:
	"""A path's end, which has to be something a table actually stores."""
	meta = _meta(doctype)
	if fieldname in _STANDARD or (meta.istable and fieldname in child_table_fields):
		return Column(doctype, fieldname)

	df = meta.get_field(fieldname)
	if df is None:
		raise BrokenPath(f"{doctype} has no field {fieldname}")
	if df.is_virtual or df.fieldtype in no_value_fields or df.fieldtype in table_fields:
		raise BrokenPath(f"{doctype}.{fieldname} has no column to read")
	return Column(doctype, fieldname)


def _joinable(doctype: str | None, via: str) -> str:
	"""`doctype`, if a path can join into it: a table of its own, one row per name."""
	if not doctype:
		raise BrokenPath(f"{via} does not say what it links to")
	meta = _meta(doctype)
	if meta.issingle or meta.is_virtual:
		raise BrokenPath(f"{via} links to {doctype}, which has no table to join")
	return doctype


def _meta(doctype: str):
	try:
		return frappe.get_meta(doctype)
	except frappe.DoesNotExistError:
		raise BrokenPath(f"DocType {doctype} does not exist") from None
