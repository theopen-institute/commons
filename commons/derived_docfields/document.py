"""The document half: a derived field reads through its link on a single record too.

The engine answers every *query*. A document is different: it is loaded with a
raw `SELECT *` (`Document.load_from_db`), which has no join, and then read in a
dozen ways -- `doc.as_dict()` for the desk form and both REST APIs, `doc.phone`
in a print format or a notification condition, `doc.get("phone")` in server
code. So each doctype with derived fields gets a controller subclass carrying one
descriptor per derived field, and every one of those ways reaches it.

How a value is found
--------------------
From the record's *current* link values, not from its row: follow the link to
the linked record and read the target field there, through `frappe.get_all` --
which is the engine, so a target that is itself derived joins onward in SQL.
One query per linked *doctype*, however many derived fields read from it and
however many of its records are linked to. Working from the link values means a
new record, or one whose link was just changed on the form, shows what it will
show once saved.

Child-table rows are looked up together. The first row of a table to be read
brings its siblings along -- the other rows of the same table on the same
parent -- so a document with forty item rows costs one query per linked doctype
for all forty, not forty.

Values are computed on first read and kept on the document for as long as the
links they came from stay the same; change a link and the next read looks
again. They are never pickled with it, so a cached document reads fresh.

How it fits core
----------------
* The descriptor is a `cached_property`, because that is what `get_valid_dict`
  looks for before treating a virtual field's `options` as a Python expression --
  which, for a derived Link, would evaluate the name of a doctype and fail.
* `get` is overridden the way core's own `LazyDocument` overrides it, since
  core's reads the instance dict directly and would miss a value not read yet.
* `delattr` hides a value, which is how `apply_fieldlevel_read_permissions`
  takes a field above the reader's permlevel off a document; a masked value
  (`mask_fields`) is left masked.
* Core's own field checks on save -- links exist and are not cancelled, selects
  hold one of their options, data fields are well-formed -- see derived fields
  as empty. They check what the user entered, and a derived value is not
  something anyone entered: a Link to a cancelled record should not stop the
  host from being saved.

The class
---------
Built in `import_controller`, which `install` wraps: core caches its result per
site and drops it in every process whenever the doctype's cache is cleared --
which a Custom Field save does -- so a field defined now reaches every worker on
its next read. One class per (controller, derived fieldnames), shared between
sites; whether a field is derived *on this site*, and whether the switch is on,
is asked at each read. Pickling goes through a metaclass registered with
`copyreg`, rebuilding the class from what it was built from -- core's own
extended classes, which can't be pickled by reference, included.
"""

import copyreg
from collections import defaultdict
from contextlib import contextmanager
from functools import cache, cached_property

import frappe
from frappe.model import base_document

from commons.derived_docfields import registry
from commons.derived_docfields.registry import BrokenPath, Column, Hop

# Instance-dict keys this module keeps on a document, none of them pickled.
MEMO = "_commons_derived"
PLANS = "_commons_derived_plans"
HIDDEN = "_commons_derived_hidden"


def _never(doc):  # pragma: no cover - a cached_property needs a function; the descriptor never calls it
	raise NotImplementedError


class DerivedValue(cached_property):
	"""One derived field on a document class."""

	def __init__(self, fieldname: str) -> None:
		super().__init__(_never)
		self.attrname = fieldname

	def __set_name__(self, owner, name):
		self.attrname = name

	def __get__(self, doc, owner=None):
		if doc is None:
			return self
		return read(doc, self.attrname)

	def __set__(self, doc, value):
		# Somebody's value for a field that isn't derived on this site, or one
		# that will be looked up again on the next read anyway.
		doc.__dict__[self.attrname] = value

	def __delete__(self, doc):
		doc.__dict__.setdefault(HIDDEN, set()).add(self.attrname)
		doc.__dict__.pop(self.attrname, None)


def read(doc, fieldname: str):
	"""A derived field's value on `doc`."""
	state = doc.__dict__
	if _quiet():
		return None
	if fieldname in state.get(HIDDEN, ()):
		return None
	if fieldname in ((state.get("flags") or {}).get("masked_fieldnames") or ()):
		return state.get(fieldname)

	active = registry.active_for(doc.doctype)
	if fieldname not in active:
		# Not derived on this site, or switched off: an ordinary virtual field.
		return state.get(fieldname)

	value = values(doc, active).get(fieldname)
	state[fieldname] = value
	return value


def values(doc, active: dict) -> dict:
	"""All of `doc`'s derived values, from its links as they stand."""
	plans = plans_for(doc, active)
	memo = doc.__dict__.get(MEMO)
	if memo and memo[0] == signature(doc, plans):
		return memo[1]

	batch = [doc, *(row for row in siblings(doc) if stale(row, plans))]
	found = resolve(batch, plans)
	for member in batch:
		member.__dict__[PLANS] = plans
		member.__dict__[MEMO] = (signature(member, plans), found[id(member)])
	return found[id(doc)]


def plans_for(doc, active: dict) -> dict:
	"""The plan of each of `doc`'s derived fields, kept on the document."""
	plans = doc.__dict__.get(PLANS)
	if plans is not None and not plans.keys() - active.keys():
		return plans

	plans = {}
	for fieldname in active:
		try:
			plans[fieldname] = registry.plan(doc.doctype, fieldname)
		except BrokenPath as e:
			from commons.derived_docfields.engine import report_broken

			report_broken(doc.doctype, fieldname, e)
	doc.__dict__[PLANS] = plans
	return plans


def signature(doc, plans: dict) -> tuple:
	"""What `doc`'s derived values were computed from: the host fields the plans start at."""
	return tuple(doc.__dict__.get(fieldname) for fieldname in sorted(sources_on_host(plans.values())))


def stale(doc, plans: dict) -> bool:
	memo = doc.__dict__.get(MEMO)
	return not memo or memo[0] != signature(doc, plans)


def siblings(doc) -> list:
	"""The other rows of `doc`'s table, if it is a child row whose parent is still around."""
	parentfield = doc.__dict__.get("parentfield")
	parent = getattr(doc, "parent_doc", None) if parentfield else None
	if parent is None:
		return []
	rows = parent.__dict__.get(parentfield) or []
	return [row for row in rows if row is not doc and getattr(row, "doctype", None) == doc.doctype]


def sources_on_host(nodes) -> set[str]:
	"""The stored fields on the host a set of plans starts from: its links, and Dynamic Link types."""
	found = set()

	def walk(node):
		if isinstance(node, Column):
			found.add(node.fieldname)
		else:
			walk(node.link)
			if node.type_field:
				walk(node.type_field)

	for node in nodes:
		walk(node)
	return found


def resolve(docs: list, plans: dict) -> dict[int, dict]:
	"""Look up the derived values of several documents of one doctype, keyed by `id()`.

	One query per linked doctype per round, for every document and every field
	at once. In rounds because a field whose link is itself derived waits for
	that link's value: a path through a derived Link takes one round per step on
	the host. Anything beyond the host -- a target that is derived on its own
	doctype -- is the engine's, inside the one query.
	"""
	found: dict[int, dict] = {id(doc): {} for doc in docs}
	pending = {id(doc): dict(plans) for doc in docs}

	while any(pending.values()):
		wanted: dict[str, dict[str, set[str]]] = defaultdict(lambda: defaultdict(set))
		lookups = []
		ready = []
		for doc in docs:
			for fieldname, node in pending[id(doc)].items():
				# Against what earlier rounds found, never this one's: a value
				# is only known once its query has run.
				link, link_known = on_host(doc, node.link, found[id(doc)])
				kind, kind_known = (
					on_host(doc, node.type_field, found[id(doc)]) if node.type_field else (None, True)
				)
				if not (link_known and kind_known):
					continue
				ready.append((id(doc), fieldname))
				if not link:
					continue
				for target, target_node in node.targets:
					if node.type_field is not None and kind != target:
						continue
					target_field = (
						target_node.fieldname
						if isinstance(target_node, Column)
						else target_node.definition.fieldname
					)
					wanted[target][key(link)].add(target_field)
					lookups.append((id(doc), fieldname, target, key(link), target_field))

		if not ready:
			# Only a loop could leave nothing ready, and `plan` refuses loops.
			break

		rows = {}
		for target, names in wanted.items():
			fields = sorted(set().union(*names.values()) - {"name"})
			for row in frappe.get_all(
				target, filters={"name": ("in", list(names))}, fields=["name", *fields], order_by=None
			):
				rows[(target, key(row.name))] = row

		this_round = dict.fromkeys(ready)
		for doc_id, fieldname, target, name, target_field in lookups:
			if row := rows.get((target, name)):
				this_round[(doc_id, fieldname)] = row.get(target_field)
		for (doc_id, fieldname), value in this_round.items():
			found[doc_id][fieldname] = value
			del pending[doc_id][fieldname]

	return found


def key(name) -> str:
	"""A record name as the database compares it: MariaDB's collation ignores case."""
	return str(name).casefold()


def on_host(doc, node, found: dict):
	"""A link's value on the host, and whether it is known yet."""
	if isinstance(node, Column):
		return doc.__dict__.get(node.fieldname), True
	fieldname = node.definition.fieldname
	if fieldname in found:
		return found[fieldname], True
	return None, False


# Staying out of core's field checks
# ----------------------------------


def _quiet() -> bool:
	return bool(getattr(frappe.local, "commons_derived_quiet", 0))


@contextmanager
def quiet():
	"""Derived fields read as empty inside: core's checks of entered values run here."""
	frappe.local.commons_derived_quiet = getattr(frappe.local, "commons_derived_quiet", 0) + 1
	try:
		yield
	finally:
		frappe.local.commons_derived_quiet -= 1


class DerivedDocument:
	"""What every derived controller adds to the controller it extends."""

	_commons_derived_fields: tuple[str, ...] = ()

	def get(self, key, filters=None, limit=None, default=None):
		if filters is None and isinstance(key, str) and key in self._commons_derived_fields:
			value = getattr(self, key)
			return default if value is None else value
		return super().get(key, filters, limit, default)

	def _validate_links(self):
		with quiet():
			return super()._validate_links()

	def _validate(self):
		with quiet():
			return super()._validate()

	def __getstate__(self):
		state = super().__getstate__()
		for key in (MEMO, PLANS, HIDDEN, *self._commons_derived_fields):
			state.pop(key, None)
		return state

	def __reduce__(self):
		return (_new_instance, (type(self),), self.__getstate__())


def _new_instance(cls):
	return cls.__new__(cls)


class DerivedControllerType(type):
	"""The metaclass of derived controllers, so they can be pickled by what built them."""


@cache
def derived_class(base: type, fieldnames: tuple[str, ...]) -> type:
	"""`base` with a descriptor for each of `fieldnames`."""
	namespace = {fieldname: DerivedValue(fieldname) for fieldname in fieldnames}
	namespace.update(
		__module__=base.__module__,
		_commons_derived_fields=fieldnames,
		_commons_derived_base=base,
	)
	return DerivedControllerType(f"Derived{base.__name__}", (DerivedDocument, base), namespace)


def _reduce_class(cls):
	base = cls._commons_derived_base
	if base.__dict__.get("__reduce__") is getattr(base_document, "_reduce_extended_instance", None):
		# One of core's `extend_doctype_class` classes, itself built at runtime:
		# rebuilt from its bases, as core rebuilds it.
		return (_rebuild_class, (True, base.__bases__, cls._commons_derived_fields))
	return (_rebuild_class, (False, (base,), cls._commons_derived_fields))


def _rebuild_class(extended: bool, bases: tuple, fieldnames: tuple[str, ...]) -> type:
	base = base_document._create_extended_class(bases) if extended else bases[0]
	return derived_class(base, fieldnames)


copyreg.pickle(DerivedControllerType, _reduce_class)


# Installing
# ----------


def install() -> bool:
	"""Wrap core's `import_controller` so derived doctypes get a derived controller.

	Idempotent. Returns whether the wrapper is in place.
	"""
	original = base_document.import_controller
	if getattr(original, "_commons_derived", False):
		return True

	def import_controller(doctype):
		class_ = original(doctype)
		try:
			fields = registry.definitions().get(doctype)
		except Exception:
			# Never the reason a controller fails to load: at worst, this
			# doctype's derived fields read as empty until the next import.
			return class_
		if not fields:
			return class_
		return derived_class(class_, tuple(sorted(fields)))

	import_controller._commons_derived = True
	import_controller.__wrapped__ = original
	base_document.import_controller = import_controller
	# Controllers imported before the wrapper was in place don't have it.
	frappe.controllers.clear()
	frappe.lazy_controllers.clear()
	return True
