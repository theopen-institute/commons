"""What this app calls itself on the site that runs it, and which of Frappe's
own behaviours it is allowed to change.

The second half is `commons.commons_core.settings.feature_enabled`. Each of
those is opt-in: a site gets core's behaviour until somebody ticks the box.

The title came first, because one thing was hard-coded: the sidebar said `Commons` under
the workspace whatever the site was, and the browser tab said it too. That is a
name, and a name is the site's to choose -- an organisation running this app
does not necessarily call the thing its staff open "Commons".

The default lives in two places on purpose. Here as the field's default, so the
form opens filled in rather than blank; and in
`commons.commons_core.settings.DEFAULT_TITLE`, which is what answers for a site
whose Single has never been saved and therefore has no row to read at all.
"""

from frappe.model.document import Document

from commons.banking.internal_transfers import clear_existing_when_switched_on


class CommonsSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		from commons.data_sync.doctype.data_sync_doctype.data_sync_doctype import DataSyncDoctype

		attendance_course_plan_field: DF.Data | None
		attendance_course_plan_hours_column: DF.Data | None
		attendance_course_plan_type_column: DF.Data | None
		attendance_group_resolution: DF.Literal["Programme", "Course", "Both"]
		attendance_inactive_term_field: DF.Data | None
		attendance_late_credit: DF.Float
		attendance_late_field: DF.Data | None
		attendance_leave_counts_as: DF.Literal["Absent", "Excused"]
		attendance_session_details_field: DF.Data | None
		attendance_session_hours_field: DF.Data | None
		attendance_session_type_field: DF.Data | None
		change_request_allow_self_approval: DF.Check
		change_request_applying_outcome: DF.Data | None
		data_sync_doctypes: DF.Table[DataSyncDoctype]
		data_sync_source_url: DF.Data | None
		enable_bikram_sambat: DF.Check
		enable_clearing_internal_transfers: DF.Check
		enable_derived_docfields: DF.Check
		enable_desk_todos: DF.Check
		enable_desktop_from_navigation_apps: DF.Check
		enable_home_page_priority: DF.Check
		enable_loan_vouchers_on_own_dates: DF.Check
		enable_navigation_rail: DF.Check
		enable_party_on_payable_payment_lines: DF.Check
		enable_payroll_lines_per_employee: DF.Check
		enable_pseudo_islands: DF.Check
		enable_sidebar_memory: DF.Check
		enable_unencoded_at_in_routes: DF.Check
		enable_user_menu: DF.Check
		enable_user_permission_gate: DF.Check
		enable_visual_email_editor: DF.Check
		expense_unassigned_open: DF.Check
		landing_page: DF.Literal[
			"",
			"Announcements",
			"Account Balance",
			"Leave Request",
			"Expense Claim",
			"Procurement",
			"Attendance",
			"Bank Reconciliation",
			"Document Capture",
		]
		procurement_group_by: DF.Data | None
		title: DF.Data | None
	# end: auto-generated types

	def on_update(self):
		clear_existing_when_switched_on(self)
