"""What a derived field has to be before it is saved, and the advice given as it is.

Doc events on Custom Field, which is where every derived field is born: the
Custom Field form, Customize Form (which saves Custom Fields for the rows it
adds), and fixture sync all go through them.

`normalize` runs first (`before_validate`) and makes the field what a derived
field is: virtual -- so core creates no column and writes nothing -- read-only,
and without the stored-field properties that mean nothing without a column.
It also refuses to undo that: a derived field whose Derived From is cleared
would be left virtual and unread (`refuse_underiving`). `check` then refuses
anything that can't resolve, and is the only place the permissions of the
doctypes along a path are consulted: whoever defines the field must be able to
read everything it reads. After that the field belongs to the host doctype
(see `commons.derived_docfields`).

The checks run when the definition changes, not on every save, so relabelling
a derived field while the feature is switched off still works.
"""

import frappe
from frappe import _
from frappe.model.meta import get_default_df

from commons.derived_docfields import registry
from commons.derived_docfields.registry import (
	CANDIDATES,
	DERIVED_FROM,
	IN_WILDCARD,
	BrokenPath,
	Column,
	Hop,
)

# What changes a definition, as opposed to its label or placement.
DEFINING = (DERIVED_FROM, CANDIDATES, "dt", "fieldname", "fieldtype", "options")

# Properties of a stored field that a derived one can't have: there is no value
# to require, default, make unique, index or search.
STORED_ONLY = {
	"reqd": 0,
	"unique": 0,
	"search_index": 0,
	"in_global_search": 0,
	"default": None,
	"fetch_from": None,
	"fetch_if_empty": 0,
	"allow_on_submit": 0,
	"set_only_once": 0,
}

# Fieldtypes whose values can stand for each other. A derived field may take a
# different fieldtype from its source within a family (a Link shown as Data),
# not across one (a Date shown as Int).
FAMILIES = {
	"text": {
		"Data",
		"Small Text",
		"Text",
		"Long Text",
		"Text Editor",
		"Markdown Editor",
		"HTML Editor",
		"Code",
		"Read Only",
		"Phone",
		"Autocomplete",
		"Select",
		"Link",
		"Dynamic Link",
		"Barcode",
		"Color",
		"Icon",
		"Signature",
		"Attach",
		"Attach Image",
		"JSON",
	},
	"whole number": {"Int", "Check"},
	"number": {"Float", "Currency", "Percent", "Rating", "Duration"},
	"date": {"Date"},
	"date and time": {"Datetime"},
	"time": {"Time"},
}

# Where the advice in the module notes starts to matter.
LARGE_TABLE = 100_000
MANY_STEPS = 3
MANY_CANDIDATES = 5


def normalize(doc, method=None) -> None:
	"""Make a Custom Field with a Derived From into a derived field, before core validates it."""
	if not (doc.get(DERIVED_FROM) or "").strip():
		refuse_underiving(doc)
		doc.set(DERIVED_FROM, None)
		doc.set(CANDIDATES, None)
		doc.set(IN_WILDCARD, 0)
		return

	doc.set(DERIVED_FROM, doc.get(DERIVED_FROM).strip())
	doc.is_virtual = 1
	doc.read_only = 1
	for fieldname, value in STORED_ONLY.items():
		doc.set(fieldname, value)
	if doc.fieldtype == "Link":
		# Core builds User Permission conditions from every Link on a doctype,
		# addressing each as a column (`Engine.get_user_permission_conditions`,
		# and the legacy `db_query` too); a derived Link has none, so every list
		# for a user with User Permissions on its target would fail. The rows
		# are narrowed by the host's own links, which is where those rules belong.
		doc.ignore_user_permissions = 1


def refuse_underiving(doc) -> None:
	"""A derived field can't have its Derived From taken away; it has to be replaced.

	Clearing it would leave what `normalize` made -- a virtual field, with a
	derived Link's doctype or a Select's choices in `options` -- but no longer a
	derived one, so the host's controller loses the descriptor that stood in
	front of those options. Core then evaluates a virtual field's `options` as
	Python on every `as_dict` (`get_valid_dict`), and every form and REST read
	of the host fails. Making it an ordinary stored field instead would need a
	column, created empty and filled by nobody -- not what anyone clearing the
	box expects -- so the change is refused and the way out named.
	"""
	if doc.is_new() or not (before := doc.get_doc_before_save()):
		return
	if not (before.get(DERIVED_FROM) or "").strip():
		return
	frappe.throw(
		_(
			"{0} is a derived field: it has no column, so it can't stop being derived. To store a value "
			"here instead, delete this field and add a new one."
		).format(frappe.bold(doc.fieldname)),
		title=_("Derived field"),
	)


def check(doc, method=None) -> None:
	"""Refuse a derived field that can't resolve, or that its author can't read."""
	if not doc.get(DERIVED_FROM):
		return
	if not doc.is_new() and not any(doc.has_value_changed(fieldname) for fieldname in DEFINING):
		return

	if not registry.enabled() and not unattended():
		frappe.throw(
			_(
				"Derived fields can only be defined while Enable Derived Docfields is ticked in Commons Settings."
			),
			title=_("Derived Docfields are off"),
		)

	if not doc.is_new() and (before := doc.get_doc_before_save()) and not before.is_virtual:
		frappe.throw(
			_(
				"{0} stores its values in a column, so it can't become a derived field: its data would be "
				"orphaned. Add a new field for the derived value instead."
			).format(frappe.bold(doc.fieldname)),
			title=_("Stored field"),
		)

	definition = registry.parse(
		doc.dt, doc.fieldname, doc.get(DERIVED_FROM), doc.get(CANDIDATES), doc.get(IN_WILDCARD)
	)
	if definition is None:
		frappe.throw(
			_("Derived From must be written <code>link_field.target_field</code>, as in Fetch From."),
			title=_("Invalid Derived From"),
		)
	if definition.link_field == doc.fieldname:
		frappe.throw(_("A derived field can't follow itself."), title=_("Invalid Derived From"))
	if doc.fieldtype == "Dynamic Link":
		# Core finds every Dynamic Link on the site by querying Custom Field
		# without regard to `is_virtual` (`frappe.model.dynamic_links`), and then
		# queries each one's column whenever anything is deleted. A value read
		# *through* a Dynamic Link is fine; a derived field that *is* one is not.
		frappe.throw(
			_("A derived field can't be a Dynamic Link. Show the value as Data instead."),
			title=_("Incompatible fieldtype"),
		)

	try:
		node = registry.plan(doc.dt, doc.fieldname, overlay=definition)
	except BrokenPath as e:
		frappe.throw(str(e), title=_("Invalid Derived From"))

	check_readable(node)
	match_source(doc, node)
	if not unattended():
		warn_about_performance(doc, node, definition)


def unattended() -> bool:
	"""Whether this save is a deploy's rather than a person's: nobody to refuse or to warn."""
	flags = frappe.flags
	return bool(flags.in_migrate or flags.in_install or flags.in_import or flags.in_patch)


# The path
# --------


def steps(root: Hop):
	"""Every (doctype, fieldname) a derived field reads on its way, and every doctype it enters.

	Everything but the field itself -- including fields on the host, which a
	path reads too: the link it starts from, and the host again if a link
	leads back to it (an Employee's manager is an Employee).
	"""
	fields, doctypes = [], []

	def walk(node):
		fields.append(
			(node.doctype, node.fieldname if isinstance(node, Column) else node.definition.fieldname)
		)
		if isinstance(node, Hop):
			children(node)

	def children(node: Hop):
		walk(node.link)
		if node.type_field:
			walk(node.type_field)
		for target, target_node in node.targets:
			if target not in doctypes:
				doctypes.append(target)
			walk(target_node)

	children(root)
	return fields, doctypes


def check_readable(node: Hop) -> None:
	"""The author has to be able to read every doctype and field the path reads.

	This is the one permission check against the source doctypes: once defined,
	the field shows whatever it reads to whoever may read the host.
	"""
	fields, doctypes = steps(node)
	for doctype in doctypes:
		if not frappe.has_permission(doctype, "read"):
			frappe.throw(
				_("You can't read {0}, so you can't define a field that shows its values.").format(
					frappe.bold(doctype)
				),
				frappe.PermissionError,
			)
	for doctype, fieldname in fields:
		meta = frappe.get_meta(doctype)
		df = meta.get_field(fieldname)
		permlevel = df.permlevel if df else 0
		if permlevel and permlevel not in meta.get_permlevel_access("read"):
			frappe.throw(
				_("You can't read {0}, so you can't define a field that shows it.").format(
					frappe.bold(f"{doctype}.{fieldname}")
				),
				frappe.PermissionError,
			)


def sources(node) -> list:
	"""The fields a derived field shows directly: its target on each target doctype."""
	return [(target, target_node) for target, target_node in node.targets] if isinstance(node, Hop) else []


def source_df(doctype: str, target_node):
	fieldname = target_node.fieldname if isinstance(target_node, Column) else target_node.definition.fieldname
	if fieldname == "name":
		# Core types `name` as Data, but a record's name is exactly a Link to
		# its own doctype -- which is what a derived Link reading it shows.
		return frappe._dict(fieldname="name", fieldtype="Link", options=doctype)
	return frappe.get_meta(doctype).get_field(fieldname) or get_default_df(fieldname)


def family(fieldtype: str) -> str | None:
	return next((name for name, members in FAMILIES.items() if fieldtype in members), None)


def match_source(doc, node) -> None:
	"""The field's fieldtype has to be able to hold what it shows, and it keeps the source's masking."""
	for target, target_node in sources(node):
		df = source_df(target, target_node)
		if df is None:
			continue
		label = frappe.bold(f"{target}.{df.fieldname}")

		if family(doc.fieldtype) is None or family(doc.fieldtype) != family(df.fieldtype):
			frappe.throw(
				_("{0} is a {1}, which a {2} field can't show.").format(label, df.fieldtype, doc.fieldtype),
				title=_("Incompatible fieldtype"),
			)

		if doc.fieldtype == "Link":
			if df.fieldtype != "Link":
				frappe.throw(
					_("A derived Link has to show a Link, and {0} is a {1}.").format(label, df.fieldtype),
					title=_("Incompatible fieldtype"),
				)
			if not doc.options:
				doc.options = df.options
			elif doc.options != df.options:
				frappe.throw(
					_("{0} links to {1}, so this field has to link to {1} too.").format(label, df.options),
					title=_("Incompatible fieldtype"),
				)
		elif doc.fieldtype == "Select" and not doc.options and df.fieldtype == "Select":
			doc.options = df.options

		if df.get("mask") and not doc.get("mask"):
			# Joining a masked field unmasked would undo core's masking for everyone.
			doc.mask = 1
			if not unattended():
				frappe.msgprint(
					_("{0} is masked, so this field is masked too.").format(label),
					indicator="blue",
					alert=True,
				)


# Advice
# ------


def depth(node) -> int:
	"""How many joins the longest way through the path takes."""
	if isinstance(node, Column):
		return 0
	through_link = depth(node.link)
	return through_link + 1 + max((depth(target_node) for _target, target_node in node.targets), default=0)


def estimated_rows(doctype: str) -> int:
	"""MariaDB's own estimate of a table's size: cheap, and near enough for advice."""
	rows = frappe.db.sql(
		"select table_rows from information_schema.tables where table_schema = database() and table_name = %s",
		(f"tab{doctype}",),
	)
	return int(rows[0][0] or 0) if rows else 0


def warn_about_performance(doc, node, definition) -> None:
	"""The module notes' advice, said at the moment it applies. Never refuses."""
	warnings = []
	meta = frappe.get_meta(doc.dt)
	link_df = meta.get_field(definition.link_field)
	large = estimated_rows(doc.dt) > LARGE_TABLE

	if doc.in_standard_filter and link_df and not link_df.search_index and not link_df.is_virtual:
		warnings.append(
			_(
				"Filtering by this field will read every {0} row, because {1} is not indexed. Tick Search Index on {1} to let the filter use an index."
			).format(doc.dt, frappe.bold(link_df.label or link_df.fieldname))
		)
	if large and (meta.sort_field or "").split(",")[0].split(" ")[0] == doc.fieldname:
		warnings.append(
			_(
				"{0} is sorted by this field by default, and has over {1} rows: every list will read and sort all of them. A stored field (Fetch From) sorts from an index."
			).format(doc.dt, f"{LARGE_TABLE:,}")
		)
	if (steps_taken := depth(node)) > MANY_STEPS:
		warnings.append(
			_(
				"This field takes {0} joins to reach its value. Each one adds a lookup for every row shown."
			).format(steps_taken)
		)
	if len(definition.candidates) > MANY_CANDIDATES:
		warnings.append(
			_(
				"{0} doctypes are listed. Each one is another join on every query that uses this field."
			).format(len(definition.candidates))
		)
	if definition.in_wildcard and large:
		warnings.append(
			_(
				"{0} has over {1} rows, and every query for all of its fields will now pay for this field's joins, including ones with no limit."
			).format(doc.dt, f"{LARGE_TABLE:,}")
		)

	if warnings:
		frappe.msgprint(
			"<br><br>".join(warnings),
			title=_("Derived field saved, with a performance note"),
			indicator="orange",
		)


# After migrate
# -------------


def check_all() -> None:
	"""Report derived fields that an upgrade or a change elsewhere has broken.

	`after_migrate`, because a migrate is when doctypes along somebody's path
	most often change. Reported, not repaired: the engine already reads a
	broken field as empty, and what it should read instead is a person's call.
	"""
	if not registry.enabled():
		return
	registry.clear()
	for doctype, fields in registry.definitions().items():
		for fieldname in fields:
			try:
				registry.plan(doctype, fieldname)
			except BrokenPath as e:
				frappe.log_error(
					title=f"Derived field {doctype}.{fieldname} does not resolve",
					message=f"{e}\n\nFound after migrate. It reads as empty until its Derived From is fixed.",
				)
