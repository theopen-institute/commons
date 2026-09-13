# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Which doctypes may have gated roles, and what each gate demands.

The split is deliberate. This document says a doctype is *gateable* and names
the User Permission that satisfies its gate; the Role Permission Manager says
which *roles* are actually gated. Neither half does anything alone, and the
half an administrator changes day to day is the one already sitting next to
the rest of the role permissions.

See `tbs_commons.safer_permissions.permissions` for how the two are enforced.
"""

import frappe
from frappe import _
from frappe.model.document import Document

from tbs_commons.safer_permissions.permissions import GATE, constraining_doctypes, is_gateable


class PermissionGateSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from tbs_commons.safer_permissions.doctype.permission_gate_rule.permission_gate_rule import (
			PermissionGateRule,
		)

		rules: DF.Table[PermissionGateRule]
	# end: auto-generated types

	def validate(self) -> None:
		seen = set()

		for rule in self.rules:
			# A child table carries no permissions of its own -- core resolves
			# it against its parent -- so gating one would silently do nothing.
			if frappe.get_meta(rule.document_type).istable:
				frappe.throw(
					_("Row {0}: {1} is a child table. Gate its parent doctype instead.").format(
						rule.idx, frappe.bold(rule.document_type)
					)
				)

			# A User Permission only narrows rows it can reach: the doctype
			# itself, or a link field pointing at it. Demanding an unreachable
			# one would produce a gate that opens without restricting anything.
			if rule.required_user_permission not in constraining_doctypes(rule.document_type):
				frappe.throw(
					_("Row {0}: a User Permission for {1} does not restrict {2}, which has no link field to it.").format(
						rule.idx,
						frappe.bold(rule.required_user_permission),
						frappe.bold(rule.document_type),
					)
				)

			pair = (rule.document_type, rule.required_user_permission)
			if pair in seen:
				frappe.throw(
					_("Row {0}: {1} already requires a User Permission for {2}.").format(
						rule.idx, frappe.bold(rule.document_type), frappe.bold(rule.required_user_permission)
					)
				)
			seen.add(pair)

	def on_update(self) -> None:
		self.clear_cache()
		self._warn_about_pending_doctypes()
		self._warn_about_orphaned_gates()

	def _warn_about_pending_doctypes(self) -> None:
		"""Say plainly which rows are not enforcing anything yet.

		`Permission Type` records can only be written during install, migrate
		or developer mode, so a row added from the desk has no checkbox until
		the next migrate. Until then no role can be gated on it -- the gate is
		inert rather than half-applied -- but an administrator who is not told
		so will assume otherwise.
		"""
		pending = sorted({rule.document_type for rule in self.rules if not is_gateable(rule.document_type)})
		if not pending:
			return

		frappe.msgprint(
			_("Run {0} to add the {1} checkbox for: {2}.").format(
				frappe.bold("bench migrate"),
				frappe.bold(_(frappe.unscrub(GATE))),
				frappe.bold(", ".join(pending)),
			),
			title=_("Not yet enforced"),
			indicator="orange",
		)

	def _warn_about_orphaned_gates(self) -> None:
		"""Catch a rule removed from under a gate that is still ticked.

		Deleting the row does not untick anybody. The roles stay gated, and
		with nothing left to name the User Permission they need, the gate
		falls back to accepting any permission that narrows the doctype --
		weaker than what was configured, and silent about it. Say so here,
		where somebody is looking, rather than only in the log.
		"""
		listed = {rule.document_type for rule in self.rules}
		orphaned = sorted(
			doctype
			for doctype in frappe.get_all("Permission Type", filters={"perm_type": GATE}, pluck="doc_type")
			if doctype not in listed
		)
		if not orphaned:
			return

		frappe.msgprint(
			_(
				"{0} still has gated roles but no rule here, so the gate no longer names the User "
				"Permission it should require. Restore the rule, or untick {1} for every role on "
				"that doctype in the Role Permission Manager."
			).format(frappe.bold(", ".join(orphaned)), frappe.bold(_(frappe.unscrub(GATE)))),
			title=_("Gate left without a rule"),
			indicator="red",
		)
