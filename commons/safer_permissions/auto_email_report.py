"""The fourth way to a report's rows: Auto Email Report.

`commons.safer_permissions.permissions` refuses a gated role the Query and
Script Reports that ignore its User Permissions, by standing in front of the
three endpoints the desk runs a report through. An Auto Email Report reaches the
same rows without any of them. It calls `Report.get_data` directly, as the
report's own `user`, from the scheduler and from its `send_now` and `download`
buttons -- so a gated user who could set one up would be mailed the report the
desk refuses them.

So the refusal is made here too, at the one method every route passes through
(`get_report_content`), and again when the document is saved, where the person
setting it up can still be told why rather than finding an Error Log later.
Both ask `gated_report_doctype` about the report's `user`, which is whose
permissions the report runs with -- not whoever pressed the button.
"""

import frappe
from frappe import _

from commons.safer_permissions.permissions import gated_report_doctype


class GatedAutoEmailReport:
	"""Mixed into `Auto Email Report` by `extend_doctype_class`; see the module docstring."""

	def validate(self):
		super().validate()
		if self.get("enabled"):
			self.refuse_if_gated()

	def get_report_content(self):
		self.refuse_if_gated()
		return super().get_report_content()

	def refuse_if_gated(self) -> None:
		ref_doctype = gated_report_doctype(self.report, self.user)
		if not ref_doctype:
			return
		frappe.throw(
			_(
				"{0}'s access to {1} is restricted to specific records, and this report cannot honour "
				"that restriction, so it cannot be emailed to them."
			).format(self.user, _(ref_doctype)),
			frappe.PermissionError,
			title=_("Not permitted"),
		)
