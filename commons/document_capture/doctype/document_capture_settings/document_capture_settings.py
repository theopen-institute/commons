"""What this site captures, and who sees which capture.

A Single, so a System Manager can change it in the desk without a deploy. The
rules it holds were the app's own until they were made the site's: which kinds
of scan are taken in, who besides the sender sees a capture of each kind, the
role that sees all of them, and the words a supplier's name is matched without.

Every default is the rule as it was hard-coded, so a site that never opens the
form behaves as it did. The defaults are also in
`commons.document_capture.settings.DEFAULTS`, which answers between this app
landing and the migrate that creates this doctype; a test holds the two equal.
"""

from frappe.model.document import Document


class DocumentCaptureSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		enable_expense_claims: DF.Check
		enable_purchase_invoices: DF.Check
		supplier_legal_words: DF.SmallText | None
	# end: auto-generated types

	pass
