"""Stop the self-service workflow mailing a PDF of every request.

The workflow was seeded with `send_email_alert`, which is not the "tell the
reviewers" switch it reads as. Frappe's `get_common_email_args` calls
`attach_print` unconditionally, so every transition mailed each reviewer a PDF
of the document -- and a `Record Change Request` is a proposal about somebody's
own record, which under the bank-account policy means an account number and an
IBAN leaving the system as an email attachment.

A patch rather than a change to `sync_change_workflow`, because that function
deliberately never rewrites an existing workflow: a site that tuned who may
approve what should not have it undone by a deploy. This is the exception that
proves the rule -- it is not a business rule anyone tuned, it is a default that
should not have shipped -- so it is applied once, narrowly, and never again.
"""

import frappe

from tbs_commons.self_service.install import DOCTYPE


def execute() -> None:
	for name in frappe.get_all(
		"Workflow",
		filters={"document_type": DOCTYPE, "send_email_alert": 1},
		pluck="name",
	):
		# `db_set` on the row rather than a save: a workflow this app seeded may
		# since have been edited into a shape its own validation now rejects, and
		# a patch that refuses to apply because of an unrelated edit is a patch
		# that leaves the attachment going out.
		frappe.db.set_value("Workflow", name, "send_email_alert", 0)
