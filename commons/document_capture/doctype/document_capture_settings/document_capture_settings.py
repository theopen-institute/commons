"""Which kinds of capture this site takes in, the extra words a supplier's
name is matched without, what every document-reading prompt is told about this
site (Additional Instructions and the local tax terms, read by
`commons.document_capture.locale`, bank statement import included), and how
many reads a person may have in an hour.

A Single, so a System Manager can change it in the desk without a deploy. Each
default is the rule as it was hard-coded, so a site that never opens the form
behaves as it did. Read through `commons.document_capture.settings`.
"""

from frappe.model.document import Document


class DocumentCaptureSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		additional_instructions: DF.SmallText | None
		enable_expense_claims: DF.Check
		enable_purchase_invoices: DF.Check
		hourly_limit: DF.Int
		supplier_legal_words: DF.SmallText | None
		tax_id_name: DF.Data | None
		withholding_tax_name: DF.Data | None
	# end: auto-generated types

	pass
