"""Hand Member, Faculty, Fellow and Associate Faculty over to the site that uses them.

TEMPORARY. Delete this file, and its entry in `before_migrate`, once
register.theopen.institute and register.localhost have both migrated past the
release that removed `commons/community/`. Nothing else calls it.

The four doctypes were this app's `Community` module, and only the Open
Institute's register ever held a row of them. They become that site's own:
custom doctypes in a custom `Community` module, with Member's controller
replaced by two Server Scripts. A site whose four tables are empty is left
alone, and Frappe's orphan cleanup removes the definitions there.

One thing is added rather than carried over: a Client Script that clears
Member's Membership Details when its type changes. The link names a record of
the old type, and core checks links before any validate event runs, so the
save failed before the Server Script (or the controller before it) could
repoint it -- and the field is read-only, so nobody could clear it by hand.
Cleared, the save repoints it. A type changed through the API or an import
still has to clear the field itself.

Why a `before_migrate` hook and not a patch, or a command run by hand
---------------------------------------------------------------------
Two parts of the same migrate would otherwise take the doctypes with them, and
this has to run before both:

* `sync_all` re-imports a standard doctype from its JSON whenever the stored
  one's `modified` differs, which would set `custom` back to 0 -- so the flip
  cannot happen while the files still exist, only in the migrate that finds
  them gone.
* `remove_orphan_doctypes`, later in that migrate, deletes every standard
  DocType whose controller no longer imports. Once the flip is made they are
  custom, and it passes them by.

`before_migrate` is the one place that is after the files are gone and before
either of those. Patches run after it and could do the same, but this app keeps
`patches.txt` empty.

What "everything" is
--------------------
Whatever the site added to the four is folded into the doctypes themselves,
because Customize Form and the Custom Field form both refuse a custom doctype:
left as customisations they would still apply but nobody could edit them. So
every Custom Field becomes a field of the doctype, every Property Setter becomes
the property it sets, and the Customize Form actions (Member's Auth0 buttons)
become the doctype's own, in the order the site put them in.

Except the derived fields. `derived_from` lives on Custom Field, so a derived
field can only be one (`commons.derived_docfields`), and they stay exactly as
they are -- as do the Property Setters that name one: the image and title field
of Faculty, Fellow and Associate Faculty, which a DocType's own save refuses
because it checks them against the DocType's own fields.

The check
---------
Every doctype's merged meta -- each field and every property of it, in order,
the doctype's own properties, actions, links, states and permissions -- and its
table's columns and checksum are recorded before anything is touched and
compared after. Any difference raises, naming it. `before_migrate` runs inside
one transaction, but a DocType save can issue DDL, which commits in MariaDB,
so the backup taken before the migrate is the real undo; the check is what says
whether it is needed.
"""

import json

import frappe
from frappe.cache_manager import clear_controller_cache

MODULE = "Community"
DOCTYPES = ("Member", "Faculty", "Associate Faculty", "Fellow")

# DocType-level Property Setters that are orders, not properties: folding one is
# the order of the rows it names, set through `idx`.
ORDER_PROPERTIES = {
	"field_order": "fields",
	"actions_order": "actions",
	"links_order": "links",
	"states_order": "states",
}

# The rows a DocType carries, other than its fields.
ROW_TABLES = {"actions": "DocType Action", "links": "DocType Link", "states": "DocType State"}

MEMBER_DETAILS = """\
# Point `member_details` at this member's Faculty, Associate Faculty or Fellow
# record, making one if there is none. What `commons.community.Member` did in
# `set_member_details` until the doctype became the site's; see the other
# "Member:" script, which runs the same block for a new Member.
linked = ("Faculty", "Associate Faculty", "Fellow")
name = None
if doc.member_type in linked and not (
	doc.member_details and frappe.db.exists(doc.member_type, doc.member_details)
):
	# `member_id` on the detail record is a Link to Member, so it holds a
	# Member name.
	name = frappe.db.get_value(doc.member_type, {"member_id": doc.name})

	# The detail record is named `format:{member_id}`, the Member's own name, so
	# one made before its link was set (or left by a deleted Member) sits at
	# that name with an empty or dangling `member_id`. It is this member's, so
	# claim it rather than collide with it.
	if not name and frappe.db.exists(doc.member_type, doc.name):
		details = frappe.get_doc(doc.member_type, doc.name)
		if (
			details.member_id
			and details.member_id != doc.name
			and frappe.db.exists("Member", details.member_id)
		):
			# Joined rather than `.format`ted: the sandbox refuses `str.format`.
			frappe.throw(
				_(doc.member_type) + " <b>" + doc.name + "</b> "
				+ _("already exists and belongs to Member") + " <b>" + details.member_id + "</b>",
				title=_("Duplicate Entry"),
			)
		details.member_id = doc.name
		details.save(ignore_permissions=True)
		name = details.name

	# The category is the Member's own field, and whoever may write this Member
	# has just set it. The detail record is what that setting means, not a
	# second thing to be separately permitted.
	if not name:
		details = frappe.new_doc(doc.member_type)
		details.member_id = doc.name
		details.insert(ignore_permissions=True)
		name = details.name
"""

SERVER_SCRIPTS = (
	{
		"name": "Member: full name and detail record",
		"doctype_event": "Before Save",
		"script": """\
# The name parts that are filled in, in reading order, unless one was typed.
parts = [doc.first_name, doc.middle_name, doc.last_name]
doc.full_name = (doc.full_name_manual or "").strip() or " ".join(
	part.strip() for part in parts if part and part.strip()
)

# A Member being inserted has no row yet for the detail record's `member_id` to
# point at, so its link would not validate. "Member: detail record for a new
# member" takes that case, once there is something to link to.
if not doc.is_new():
"""
		+ "\n".join("\t" + line if line else line for line in MEMBER_DETAILS.splitlines())
		+ """
	if name:
		doc.member_details = name
""",
	},
	{
		"name": "Member: detail record for a new member",
		"doctype_event": "After Insert",
		"script": MEMBER_DETAILS
		+ """
if name:
	doc.db_set("member_details", name, update_modified=False)
""",
	},
)

CLIENT_SCRIPT = {
	"name": "Member: clear Membership Details on a type change",
	"script": """\
// Membership Details names a record of the member's type, so a new type leaves
// it pointing at a record the link can no longer find, and the save fails on
// that before "Member: full name and detail record" can repoint it. The field
// is read-only, so it is cleared here; the save then finds or makes the record
// of the new type.
frappe.ui.form.on("Member", {
	member_type(frm) {
		if (frm.doc.member_details) {
			frm.set_value("member_details", null);
		}
	},
});
""",
}


def run() -> None:
	if not due():
		return

	before = {doctype: snapshot(doctype) for doctype in DOCTYPES}

	frappe.db.set_value("Module Def", MODULE, {"custom": 1, "app_name": None}, update_modified=False)
	for doctype in DOCTYPES:
		convert(doctype)
	for script in SERVER_SCRIPTS:
		add_server_script(script)
	add_client_script()

	frappe.clear_cache()
	differences = [
		f"{doctype}: {difference}"
		for doctype in DOCTYPES
		for difference in compare(before[doctype], snapshot(doctype))
	]
	if differences:
		frappe.throw(
			"Community handover changed what the doctypes are:\n" + "\n".join(differences),
			title="Community handover",
		)
	print(f"Community handover: {', '.join(DOCTYPES)} are this site's own doctypes now.")


def due() -> bool:
	"""Whether this site still has the app's four doctypes, with rows in them."""
	for doctype in DOCTYPES:
		row = frappe.db.get_value("DocType", doctype, ("custom", "module"), as_dict=True)
		if not row or row.custom or row.module != MODULE:
			return False
	return any(frappe.db.count(doctype) for doctype in DOCTYPES)


def convert(doctype: str) -> None:
	meta = frappe.get_meta(doctype, cached=False)
	custom_fields = frappe.get_all(
		"Custom Field", filters={"dt": doctype}, fields=["name", "fieldname", "derived_from"]
	)
	derived = {f.fieldname for f in custom_fields if f.derived_from}
	folded_fields = [f.name for f in custom_fields if not f.derived_from]

	setters = frappe.get_all(
		"Property Setter",
		filters={"doc_type": doctype},
		fields=["name", "doctype_or_field", "field_name", "property", "value"],
	)
	kept_setters = {
		s.name
		for s in setters
		if s.field_name in derived
		or (
			s.doctype_or_field == "DocType"
			and s.property in ("image_field", "title_field")
			and s.value in derived
		)
	}

	# Customize Form's rows, held under the same parent with `custom = 1` and
	# `parenttype = "Customize Form"`, so `get_doc` does not load them. Made the
	# doctype's own rows before it is loaded, so they come with it.
	for table, row_doctype in ROW_TABLES.items():
		frappe.db.set_value(
			row_doctype,
			{"parent": doctype, "custom": 1},
			{"custom": 0, "parenttype": "DocType", "parentfield": table},
			update_modified=False,
		)

	doc = frappe.get_doc("DocType", doctype)

	# Fields: the merged meta's order and properties, less the derived fields,
	# which stay Custom Fields and are placed by their own `insert_after`.
	own = {row.fieldname: row for row in doc.fields}
	field_properties = value_fields("DocField")
	rows = []
	for field in meta.fields:
		if field.fieldname in derived:
			continue
		row = own.get(field.fieldname) or frappe.new_doc("DocField", parent_doc=doc, parentfield="fields")
		for prop in field_properties:
			row.set(prop, field.get(prop))
		rows.append(row)
	doc.set("fields", rows)

	# Actions, links and states, in the order the site gave them.
	for table in ROW_TABLES:
		by_name = {row.name: row for row in doc.get(table)}
		doc.set(table, [by_name[row.name] for row in meta.get(table) if row.name in by_name])

	for setter in setters:
		if setter.name in kept_setters or setter.doctype_or_field != "DocType":
			continue
		if setter.property not in ORDER_PROPERTIES:
			doc.set(setter.property, meta.get(setter.property))

	for table in ("fields", *ROW_TABLES):
		for index, row in enumerate(doc.get(table), start=1):
			row.idx = index

	# Gone before the save, so nothing reading the meta during it sees a field
	# twice. `db.delete` rather than `delete_doc`: a Custom Field's `on_trash`
	# deletes its Property Setters too, and those are decided on above.
	if folded_fields:
		frappe.db.delete("Custom Field", {"name": ("in", folded_fields)})
	folded_setters = [s.name for s in setters if s.name not in kept_setters]
	if folded_setters:
		frappe.db.delete("Property Setter", {"name": ("in", folded_setters)})

	# Stored first as well: the save's own checks look the controller up from the
	# stored row, and for a standard doctype that is an import of the module
	# this release deleted.
	frappe.db.set_value("DocType", doctype, "custom", 1, update_modified=False)
	clear_controller_cache(doctype)
	doc.custom = 1
	doc.save(ignore_permissions=True)
	frappe.clear_cache(doctype=doctype)


def add_server_script(script: dict) -> None:
	if frappe.db.exists("Server Script", script["name"]):
		return
	frappe.get_doc(
		{
			"doctype": "Server Script",
			"name": script["name"],
			"script_type": "DocType Event",
			"reference_doctype": "Member",
			"module": MODULE,
			**script,
		}
	).insert(ignore_permissions=True)


def add_client_script() -> None:
	"""Also run by hand on a site the handover has already converted."""
	if frappe.db.exists("Client Script", CLIENT_SCRIPT["name"]):
		return
	frappe.get_doc(
		{
			"doctype": "Client Script",
			"dt": "Member",
			"view": "Form",
			"enabled": 1,
			"module": MODULE,
			**CLIENT_SCRIPT,
		}
	).insert(ignore_permissions=True)


def value_fields(doctype: str) -> list[str]:
	return [
		df.fieldname
		for df in frappe.get_meta(doctype).fields
		if df.fieldtype not in frappe.model.no_value_fields
	]


def snapshot(doctype: str) -> dict:
	"""Everything a reader, a form or a query gets from this doctype."""
	meta = frappe.get_meta(doctype, cached=False)
	skip = {"custom", "modified", "modified_by", "creation", "owner", *ORDER_PROPERTIES}
	rows = {
		table: [
			{prop: norm(row.get(prop)) for prop in value_fields(row_doctype) if prop != "custom"}
			for row in meta.get(table)
		]
		for table, row_doctype in {**ROW_TABLES, "permissions": "DocPerm"}.items()
	}
	table = f"tab{doctype}"
	return {
		"doctype": {prop: norm(meta.get(prop)) for prop in value_fields("DocType") if prop not in skip},
		"fields": [
			(field.fieldname, {prop: norm(field.get(prop)) for prop in value_fields("DocField")})
			for field in meta.fields
		],
		**rows,
		"columns": frappe.db.sql(
			"""select column_name, column_type, is_nullable, column_default, column_key
			from information_schema.columns where table_schema = database() and table_name = %s
			order by column_name""",
			table,
		),
		"checksum": frappe.db.sql(f"checksum table `{table}`")[0][1],
		"rows": frappe.db.count(doctype),
	}


def compare(before: dict, after: dict) -> list[str]:
	differences = []
	for key in before:
		if key == "fields":
			order_before = [name for name, _ in before[key]]
			order_after = [name for name, _ in after[key]]
			if order_before != order_after:
				differences.append(f"field order {order_before} became {order_after}")
			after_fields = dict(after[key])
			for name, props in before[key]:
				for prop, value in props.items():
					if name in after_fields and after_fields[name].get(prop) != value:
						differences.append(f"{name}.{prop} {value!r} became {after_fields[name].get(prop)!r}")
		elif key == "doctype":
			for prop, value in before[key].items():
				if after[key].get(prop) != value:
					differences.append(f"{prop} {value!r} became {after[key].get(prop)!r}")
		elif before[key] != after[key]:
			differences.append(
				f"{key} {json.dumps(before[key], default=str)} became {json.dumps(after[key], default=str)}"
			)
	return differences


def norm(value):
	"""One spelling for "not set", and for numbers, whichever table they came from."""
	if value in (None, "", 0, "0"):
		return None
	if isinstance(value, bool | int | float):
		return str(float(value))
	return str(value)
