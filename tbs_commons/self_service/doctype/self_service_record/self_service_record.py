"""Which doctypes people may read their own records of, and what they may propose.

This is the configuration the self-service section runs on, held as documents
rather than as code. It used to be a `self_service_records` hook pointing at
dicts in `tbs_commons.self_service.policies`, which meant that adding a field to
the employee profile -- or taking one off it -- was a deploy. It is a decision
about what staff may see about themselves, which is an administrator's to make
and to be able to review, so it belongs where they can see and change it.

A record answers four questions, and deliberately not a fifth.

*Which doctype*, and whether it is on at all. A doctype with no enabled record
here is not self-service, whatever anyone's permissions say -- see
`registry.policy`, which refuses rather than defaulting.

*Whose record is it.* `owner_field` names the field that says so. A Link to User
names the owner outright, which is how `Employee` works through `user_id`. With
`owner_doctype` set the field names another self-service record instead and
ownership chains through it -- a bank account names its `Employee`, and whoever
owns that employee owns it. That is what lets a second record type be added as a
document rather than as another idea of what "mine" means.

*Which records count*, through `record_filters` -- `{"status": "Active"}` stops a
leaver's record being theirs to read -- and whether there is one per owner or
several.

*Which fields, grouped how*, through the `fields` table: a section, an order, and
two checkboxes.

The fifth question, deliberately unanswered here: what a field is called, what
type it is, what its options are, whether it is mandatory. All of that is read
from `frappe.get_meta` on the doctype itself when the page asks -- see
`registry.field_definitions`. Restating it would mean a label that drifts from
the one the desk shows and a select whose options are a year out of date.
"""

import json

import frappe
from frappe import _
from frappe.model.document import Document


class SelfServiceRecord(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from tbs_commons.self_service.doctype.self_service_field.self_service_field import (
			SelfServiceField,
		)

		document_type: DF.Link
		enabled: DF.Check
		fields: DF.Table[SelfServiceField]
		is_singular: DF.Check
		owner_doctype: DF.Link | None
		owner_field: DF.Data
		record_filters: DF.Code | None
		title_field: DF.Data | None
	# end: auto-generated types

	def validate(self) -> None:
		self.validate_owner()
		self.validate_filters()
		self.validate_fields()

	def on_update(self) -> None:
		self.clear_registry_cache()

	def on_trash(self) -> None:
		self.clear_registry_cache()

	def clear_registry_cache(self) -> None:
		"""Drop the resolved registry so the next request reads this change.

		The registry caches every enabled record for the site, which is what keeps
		a permission check off the database. A configuration change that did not
		clear it would appear to do nothing until something else did.

		Cleared again after a rollback, and that is not belt and braces. This runs
		in `on_update`, before the transaction commits, so a save that later fails
		-- a validation error further down the request, a raised exception, an
		explicit rollback -- would otherwise leave the cache holding a
		configuration the database no longer contains. The window is small and the
		symptom is baffling: a page rendering fields nobody can find in the desk.

		A rollback to a savepoint does not run these callbacks, so a test that
		saves configuration inside one still has to clear the cache itself.
		"""
		from tbs_commons.self_service import registry

		registry.clear_cache()
		frappe.db.after_rollback.add(registry.clear_cache)

	def meta_for(self):
		return frappe.get_meta(self.document_type)

	def validate_owner(self) -> None:
		"""The ownership fields have to describe a route that actually exists.

		Checked here rather than where it is followed, because a chain that dead
		ends is a configuration mistake and the person who can fix it is the one
		saving this form -- not the employee whose page quietly shows nothing.
		"""
		meta = self.meta_for()
		if not meta.has_field(self.owner_field):
			frappe.throw(
				_("{0} has no field {1} to own records by.").format(
					_(self.document_type), frappe.bold(self.owner_field)
				)
			)

		field = meta.get_field(self.owner_field)
		if self.owner_doctype:
			if self.owner_doctype == self.document_type:
				frappe.throw(_("A record type cannot own itself."))
			# Not a hard requirement that the target is configured *yet* -- the two
			# records may be saved in either order -- but it has to be a doctype.
			if not frappe.db.exists("DocType", self.owner_doctype):
				frappe.throw(_("{0} is not a doctype.").format(self.owner_doctype))
		elif field.fieldtype == "Link" and field.options != "User":
			frappe.throw(
				_(
					"{0} links to {1}, not to User. Set Owner Document Type so ownership "
					"follows that record, or choose a field that names a user."
				).format(frappe.bold(self.owner_field), field.options)
			)

		if self.title_field and not meta.has_field(self.title_field):
			frappe.throw(
				_("{0} has no field {1} to use as a title.").format(
					_(self.document_type), frappe.bold(self.title_field)
				)
			)

	def validate_filters(self) -> None:
		"""`record_filters` is JSON and has to parse, or nothing is ever owned."""
		if not (self.record_filters or "").strip():
			return
		try:
			parsed = json.loads(self.record_filters)
		except ValueError as exc:
			frappe.throw(_("Record Filters is not valid JSON: {0}").format(exc))
		if not isinstance(parsed, dict):
			frappe.throw(
				_("Record Filters must be a JSON object, such as {0}.").format('{"status": "Active"}')
			)
		meta = self.meta_for()
		for fieldname in parsed:
			if fieldname != "name" and not meta.has_field(fieldname):
				frappe.throw(
					_("Record Filters names {0}, which {1} has no field for.").format(
						frappe.bold(fieldname), _(self.document_type)
					)
				)

	def validate_fields(self) -> None:
		"""Every row names a real field, once, and nothing dangerous is proposable.

		A `Password` field is refused outright rather than merely defaulted off:
		it exists to hold a credential, it is never a fact about the person, and
		a page that showed one would be handing it back in clear.
		"""
		meta = self.meta_for()
		seen: set[str] = set()
		for row in self.fields:
			if not meta.has_field(row.fieldname):
				frappe.throw(
					_("Row {0}: {1} has no field {2}.").format(
						row.idx, _(self.document_type), frappe.bold(row.fieldname)
					)
				)
			if row.fieldname in seen:
				frappe.throw(_("Row {0}: {1} is listed twice.").format(row.idx, frappe.bold(row.fieldname)))
			seen.add(row.fieldname)

			field = meta.get_field(row.fieldname)
			if field.fieldtype == "Password":
				frappe.throw(
					_("Row {0}: {1} holds a credential and cannot be exposed here.").format(
						row.idx, frappe.bold(row.fieldname)
					)
				)
			if row.proposable and not row.viewable:
				frappe.throw(
					_("Row {0}: {1} cannot be proposable without being viewable.").format(
						row.idx, frappe.bold(row.fieldname)
					)
				)
			if row.proposable and field.read_only:
				frappe.throw(
					_("Row {0}: {1} is read only on {2}, so a change to it could never apply.").format(
						row.idx, frappe.bold(row.fieldname), _(self.document_type)
					)
				)
