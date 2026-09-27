"""An employee's receipts, read off a scan, drafted as their own Expense Claim.

The second kind of `Captured Document`, alongside `purchase_invoice`, and read
the same way: `capture` runs `read_scan` in the background and stores what
comes back, and `reading` and `create` are what the dialog calls.

Whose claim
-----------
Always the claimant's own: `create` goes through
`commons.requests.expense.request_expense_claim`, which raises a claim for
the employee behind the session and never for one the payload names. The
currency, the cost centre, the exchange rate and each expense's account are
settled there, as for a claim typed on the expenses page. So a receipt
capture can be drafted only by its owner: whoever uploaded it, or the user
who emailed it in. Anybody else would be claiming somebody else's receipt as
their own.

What is read
------------
One expense per receipt, at the total paid as printed, tax and all, because
that is what the employee is owed. The lines of a restaurant bill are not
separate expenses. The same rule as for invoices: every figure is copied off
the page, never worked out. A photo of several receipts gives one expense
each. The expense type is Claude's suggestion, from this site's own list, and
the dialog offers only the types the claimant's company can book to, so a
suggestion outside those is dropped there.
"""

import frappe
from frappe import _

from commons.api_integrations.claude import client as claude
from commons.api_integrations.claude import documents, jobs
from commons.commons_core import apps
from commons.document_capture.purchase_invoice import DATE, STRING, _nullable, _object

EXPENSE_CLAIM = "Expense Claim"
EXPENSE_CLAIM_TYPE = "Expense Claim Type"

# A few receipts' worth, with room for the effort's thinking.
MAX_TOKENS = 16000


def available() -> bool:
	"""HRMS for the claim, and a Claude key to read the receipt with."""
	return apps.has_doctype(EXPENSE_CLAIM) and claude.available()


def can_capture() -> bool:
	"""Whether this person may raise a claim of their own: the permission, and
	an employee record to raise it for."""
	from commons.api import session_employee

	if not apps.has_doctype(EXPENSE_CLAIM):
		return False
	if not frappe.has_permission(EXPENSE_CLAIM, "create"):
		return False
	return bool(session_employee(["name"]))


def _require_drafting() -> None:
	if not apps.has_doctype(EXPENSE_CLAIM):
		frappe.throw(_("Expense claims are not set up on this site."))
	if not can_capture():
		frappe.throw(_("You cannot raise an expense claim."), frappe.PermissionError)


# --------------------------------------------------------------------------- #
# Reading the scan                                                            #
# --------------------------------------------------------------------------- #


def schema(expense_types: list[str]) -> dict:
	"""The receipts' fields, with the site's expense types to choose from."""
	expense_type = (
		_nullable(
			{"type": "string", "enum": expense_types},
			"The one of our expense types this is, or null if none clearly fits.",
		)
		if expense_types
		else {"type": "null"}
	)
	return _object(
		{
			"is_receipt": {
				"type": "boolean",
				"description": "Whether this is a receipt or bill for something paid for at all.",
			},
			"currency": _nullable(STRING, "ISO 4217 code."),
			"expenses": {
				"type": "array",
				"items": _object(
					{
						"merchant": _nullable(STRING, "Who was paid, as printed."),
						"receipt_number": _nullable(STRING),
						"date": _nullable(DATE),
						"description": STRING,
						"amount": _nullable(
							{"type": "number"}, "The total paid, tax included, as printed; null if illegible."
						),
						"expense_type": expense_type,
					}
				),
			},
			"notes": {"type": "array", "items": STRING},
		}
	)


INSTRUCTIONS = """\
This is a receipt, or several, for something one of our employees paid for \
themselves and is claiming back from us. Copy what it says into the schema.

Copy, don't compute. Every figure must be one that is printed on the page. If a \
figure is missing or illegible, use null and say so in notes. Never fill a gap \
with arithmetic.

- One expense per receipt, not per line on it. amount is the total the receipt \
says was paid, tax and service charge included, exactly as printed.
- Numbers are plain numbers, without currency symbols or thousands separators. \
Convert Devanagari digits (०१२३४५६७८९) to 0-9. South Asian grouping such as \
1,13,000.00 is 113000.
- description is a few words on what was paid for, from the receipt: "Taxi, \
Thamel to airport", "Lunch at Bhojan Griha", "Printer toner".
- expense_type: the one of the listed types this expense clearly is, or null.
- Dates: give each as printed, then its year, month and day. Nepali receipts \
often use Bikram Sambat (B.S. or वि.सं.), whose years currently run from about \
2075 to 2090. Mark those calendar "BS" and give the Bikram Sambat year, month \
and day as printed; do not convert them. Mark Gregorian dates "AD".
- currency: NPR for rupees on a Nepali receipt, INR on an Indian one, USD for \
US dollars, and so on; null if it cannot be told.
- If the document is not a receipt or bill for something paid (a quotation, a \
bank statement, a supplier's invoice to be paid later), set is_receipt to false \
and fill in what you can.
- notes: anything worth checking against the paper, such as handwritten \
amounts, figures you are unsure of, or a total that does not match its lines. \
Keep each note to a sentence. Leave the list empty if there is nothing to say.
"""


def read_scan(content: bytes, progress=lambda **changes: None) -> dict:
	"""What the receipts say, in the shape of `schema`. Run in `capture`'s job,
	and counted as it streams by each expense's `"description"`."""
	from commons.document_capture.capture import READ_TIMEOUT

	progress(step="reading")
	counter = jobs.RowCounter(lambda lines: progress(lines=lines))
	types = frappe.get_all(EXPENSE_CLAIM_TYPE, pluck="name", order_by="name asc")
	return documents.read(
		content,
		schema(types),
		INSTRUCTIONS,
		on_text=counter.feed,
		timeout=READ_TIMEOUT,
		max_tokens=MAX_TOKENS,
		too_long=_("That is too many receipts to read in one go. Send them a few at a time."),
	)


def reading(capture, extracted: dict) -> dict:
	"""What the dialog opens with: the reading, and what a blank claim of this
	person's would open with (their employee, approver and expense types)."""
	from commons.requests.expense import get_expense_claim_defaults

	_require_drafting()
	return {"extracted": extracted, "defaults": get_expense_claim_defaults()}


# --------------------------------------------------------------------------- #
# The draft                                                                   #
# --------------------------------------------------------------------------- #


@frappe.whitelist(methods=["POST"])
def create(capture: str, claim: dict) -> dict:
	"""Raise the claim, and mark the capture drafted with its receipt attached.

	`claim` is what `request_expense_claim` takes: the approver, a remark and
	the expenses. One request, so if the claim is refused, the capture stays
	as it was.
	"""
	from commons.document_capture import capture as captures
	from commons.requests.expense import request_expense_claim

	_require_drafting()
	source = captures.for_drafting(capture, EXPENSE_CLAIM)
	if source.owner != frappe.session.user:
		frappe.throw(
			_("{0} is {1}'s receipt. Only they can claim it.").format(source.name, source.owner),
			frappe.PermissionError,
		)
	created = request_expense_claim(claim)
	captures.link_draft(source, frappe.get_doc(EXPENSE_CLAIM, created["name"]))
	return {
		"name": created["name"],
		"total_claimed_amount": created.get("total_claimed_amount"),
		"currency": created.get("currency"),
	}
