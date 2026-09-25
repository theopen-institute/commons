"""A supplier's invoice, read off a scan, drafted as a Purchase Invoice.

Four endpoints, in the order the page calls them:

`read_invoice`
	The scan goes to Claude and comes back as the fields in `SCHEMA`, with the
	company and suppliers on this site that it most likely means. The scan is
	not stored.
`suggest`
	For the company and supplier the reader has settled on: an expense account
	for each line, the tax options, and any invoice already booked with this
	supplier's bill number. Called again whenever either choice changes.
`preview`
	ERPNext's totals for the draft as it stands, from the same document
	`create` would insert. What the dialog compares with the scan's total.
`create`
	Inserts the draft, and first the supplier too if the reader asked for a
	new one, in one transaction.

How this site books purchases, which the suggestions follow
-----------------------------------------------------------
On register.localhost almost no invoice line names an Item: 106 of 117 are free
text ("Consulting fees - Accreditation management", "Internet from Vianet
(6mo)") booked straight to an expense account. So the question each line needs
answered is which account, not which item, and the answer is read from this
company's own submitted invoices: first what this supplier's lines were booked
to, then any line described the same way, and only then the company's default
expense account, flagged for review because on a stock company that is Cost of
Goods Sold.

Taxes are the company's templates, or the rows on this supplier's last invoice,
which is how the invoices without a template here were taxed. The rows are
copied, not typed: an invoice's VAT account differs between the companies on
this site ("VAT In - KC", "VAT - OI-Nepal", "Tax and Fee Expenses - OI-Nepal"),
and a guess would be wrong on one of them.

Every date arrives Gregorian. The scan's date may be in Bikram Sambat, and
`SCHEMA` asks for it as printed and says which calendar. The browser converts it
with the same tables its date picker uses, and nothing here converts dates
again.

Who may use it
--------------
Whoever may create a Purchase Invoice, checked before anything is sent to
Claude, because every read is billed. There is also a per-person limit of
`HOURLY_LIMIT` reads an hour, so a script, or a stuck retry, cannot run up the
site's bill. Every read of this site's records goes through `frappe.get_list` or
a permission-checked `get_doc`, so User Permissions and
`commons.safer_permissions` narrow the suggestions exactly as they narrow the
desk.
"""

import re
from collections import Counter
from difflib import SequenceMatcher

import frappe
from frappe import _
from frappe.utils import flt, today

from commons.api_integrations.claude import client as claude
from commons.api_integrations.claude import documents
from commons.commons_core import apps

PURCHASE_INVOICE = "Purchase Invoice"
SUPPLIER = "Supplier"
COMPANY = "Company"
TAX_TEMPLATE = "Purchase Taxes and Charges Template"

# Reads per person per hour. A person working through a pile of invoices needs
# one a minute at most, and a read costs a few cents.
HOURLY_LIMIT = 60

# How far back the account suggestions look. A company here books a hundred or
# so invoices a year, so this is several years of them.
HISTORY_ROWS = 2000
SUPPLIER_ROWS = 10000

# `Purchase Invoice Item.item_name` is a Data field.
ITEM_NAME_LENGTH = 140

# How close a name or a description has to be before it counts as the same
# thing, on `similarity`'s scale. Suppliers are offered from a lower score than
# they are chosen at: a candidate is only a suggestion for the reader to accept.
SUPPLIER_OFFERED = 0.7
SUPPLIER_CHOSEN = 0.9
COMPANY_CHOSEN = 0.6
SAME_SUPPLIER_LINE = 0.5
ANY_LINE = 0.7

# Words that say what sort of company a name belongs to rather than which one.
# "Vianet Communications Pvt.Ltd" and "VIANET COMMUNICATIONS PVT. LTD." are the
# same supplier however the suffix is spelled.
LEGAL_WORDS = frozenset(
	{"pvt", "private", "ltd", "limited", "p", "co", "company", "inc", "llc", "llp", "the", "and", "m", "s"}
)


def available() -> bool:
	"""Whether this site can draft invoices from scans at all.

	ERPNext for the invoice, and a Claude key to read the scan with. Without the
	key the page is left out rather than offered with an error.
	"""
	return apps.has_doctype(PURCHASE_INVOICE) and claude.available()


def can_capture() -> bool:
	"""Whether this reader is somebody the page is for: they can raise a
	Purchase Invoice, which is all the page ever creates."""
	return bool(frappe.has_permission(PURCHASE_INVOICE, "create"))


def _require() -> None:
	if not available():
		frappe.throw(_("Reading invoices from scans is not set up on this site."))
	if not can_capture():
		frappe.throw(_("You are not allowed to create purchase invoices."), frappe.PermissionError)


# --------------------------------------------------------------------------- #
# Reading the scan                                                             #
# --------------------------------------------------------------------------- #


def _nullable(schema: dict, description: str | None = None) -> dict:
	nullable = {"anyOf": [schema, {"type": "null"}]}
	if description:
		nullable["description"] = description
	return nullable


def _object(properties: dict) -> dict:
	return {
		"type": "object",
		"properties": properties,
		"required": list(properties),
		"additionalProperties": False,
	}


STRING = {"type": "string"}
NUMBER = {"type": "number"}

DATE = _object(
	{
		"printed": {"type": "string", "description": "The date exactly as printed."},
		"year": {"type": "integer"},
		"month": {"type": "integer", "description": "1 to 12."},
		"day": {"type": "integer"},
		"calendar": {
			"type": "string",
			"enum": ["AD", "BS"],
			"description": "BS for a Bikram Sambat date, AD for a Gregorian one.",
		},
	}
)

PARTY = _object(
	{
		"name": _nullable(STRING),
		"tax_id": _nullable(STRING, "PAN, VAT or other tax registration number, as printed."),
	}
)

SCHEMA = _object(
	{
		"is_invoice": {
			"type": "boolean",
			"description": "Whether this is an invoice or bill from a supplier at all.",
		},
		"supplier": PARTY,
		"buyer": PARTY,
		"invoice_number": _nullable(STRING),
		"invoice_date": _nullable(DATE),
		"due_date": _nullable(DATE),
		"currency": _nullable(STRING, "ISO 4217 code."),
		"lines": {
			"type": "array",
			"items": _object(
				{
					"description": STRING,
					"quantity": NUMBER,
					"rate": {"type": "number", "description": "Price per unit, before tax."},
					"amount": {"type": "number", "description": "The line's total before tax, as printed."},
				}
			),
		},
		"discount": _nullable(NUMBER, "A discount on the whole invoice, as a positive amount."),
		"subtotal": _nullable(NUMBER, "The lines' total before tax, as printed."),
		"taxes": {
			"type": "array",
			"items": _object(
				{
					"label": STRING,
					"rate": _nullable(NUMBER, "In percent: 13 for 13%."),
					"amount": NUMBER,
				}
			),
		},
		"total": _nullable(NUMBER, "The final amount payable, as printed."),
		"notes": {"type": "array", "items": STRING},
	}
)

INSTRUCTIONS = """\
This is an invoice or bill that our organisation has received from a supplier. \
Copy what it says into the schema.

Copy, don't compute. Every figure must be one that is printed on the page. If a \
figure is missing or illegible, use null (or leave it out of a list) and say so \
in notes. Never fill a gap with arithmetic.

- Numbers are plain numbers, without currency symbols or thousands separators. \
Convert Devanagari digits (०१२३४५६७८९) to 0-9. South Asian grouping such as \
1,13,000.00 is 113000.
- The supplier is whoever issued the invoice; the buyer is whoever it is billed \
to. tax_id is the PAN, VAT or other tax registration number printed for that \
party.
- Dates: give each as printed, then its year, month and day. Nepali invoices \
often use Bikram Sambat (B.S. or वि.सं.), whose years currently run from about \
2075 to 2090. Mark those calendar "BS" and give the Bikram Sambat year, month \
and day as printed; do not convert them. Mark Gregorian dates "AD". If both are \
printed, give the Gregorian one.
- lines are the goods or services charged for. Leave out taxes, discounts and \
totals. quantity is 1 when none is printed; rate is the price per unit before \
tax; amount is the line's total before tax, as printed. Copy all three as \
printed even when quantity times rate does not equal the amount: the bookkeeper \
checks each line, and a corrected figure would hide what is on the paper.
- subtotal is the total of the lines before tax, where one is printed (often \
"Sub total", "Total" or "Taxable amount"); null where there is none.
- taxes are VAT, GST, sales tax or similar charges added on top, each with its \
printed rate and amount. Leave out tax withheld by the buyer (TDS).
- currency: NPR for rupees on a Nepali invoice, INR on an Indian one, USD for \
US dollars, and so on; null if it cannot be told.
- If the document is not an invoice or bill (a quotation, a delivery note, a \
bank statement), set is_invoice to false and fill in what you can.
- notes: anything a bookkeeper should check against the paper, such as \
handwritten corrections, figures you are unsure of, more than one invoice on \
the page, or totals on the page that do not add up. Keep each note to a \
sentence. Leave the list empty if there is nothing to say.
"""


@frappe.whitelist(methods=["POST"])
def read_invoice() -> dict:
	"""Read the scan in the request's `file` field.

	A multipart upload, the way Frappe's own `upload_file` receives one, so the
	browser sends the file as it is rather than base64-encoded inside JSON.
	"""
	_require()
	upload = frappe.request.files.get("file") if frappe.request else None
	if not upload:
		frappe.throw(_("Choose a scan to read."))
	_count_read()

	extracted = documents.read(upload.stream.read(), SCHEMA, INSTRUCTIONS)
	companies = _companies()
	return {
		"extracted": extracted,
		"companies": companies,
		"company": _match_company(extracted.get("buyer") or {}, companies),
		"suppliers": _match_suppliers(extracted.get("supplier") or {}),
		"model": claude.model(),
	}


def _count_read() -> None:
	"""Refuse the read past `HOURLY_LIMIT` for this person, in a rolling hour
	that starts at their first read."""
	key = frappe.cache.make_key(f"commons:document_capture:reads:{frappe.session.user}")
	count = frappe.cache.incrby(key, 1)
	if count == 1:
		frappe.cache.expire(key, 3600)
	if count > HOURLY_LIMIT:
		frappe.throw(
			_("That is {0} scans in the last hour, which is the limit. Try again later.").format(
				HOURLY_LIMIT
			),
			frappe.RateLimitExceededError,
		)


# --------------------------------------------------------------------------- #
# Which company, which supplier                                                #
# --------------------------------------------------------------------------- #


def _companies() -> list[dict]:
	return frappe.get_list(
		COMPANY,
		fields=["name", "company_name", "tax_id", "default_currency"],
		order_by="name asc",
		limit=100,
	)


def _match_company(buyer: dict, companies: list[dict]) -> dict:
	"""The company the invoice is billed to, and why that one.

	The tax number first, since it is the one thing on an invoice that is
	unambiguous; then the name; then the reader's default company, which is
	a guess, and the reason says so.
	"""
	tax_id = _digits(buyer.get("tax_id"))
	if tax_id:
		for company in companies:
			if _digits(company.tax_id) == tax_id:
				return {"name": company.name, "reason": _("The tax number the invoice is billed to")}

	billed_to = buyer.get("name") or ""
	scored = sorted(
		(
			(similarity(billed_to, company.company_name or company.name), company.name)
			for company in companies
		),
		reverse=True,
	)
	if scored and scored[0][0] >= COMPANY_CHOSEN:
		return {"name": scored[0][1], "reason": _("The invoice is billed to “{0}”").format(billed_to)}

	names = [company.name for company in companies]
	default = frappe.defaults.get_user_default("Company")
	if default in names:
		reason = (
			_("Your default company. The invoice is billed to “{0}”, which matches none.").format(billed_to)
			if billed_to
			else _("Your default company. The invoice does not say who it is billed to.")
		)
		return {"name": default, "reason": reason}
	if len(names) == 1:
		return {"name": names[0], "reason": None}
	return {"name": None, "reason": None}


def _match_suppliers(supplier: dict) -> list[dict]:
	"""The suppliers on this site the invoice might be from, best first.

	At most five, each with its reason. `strong` marks one close enough for
	the dialog to choose it without being asked; anything else is offered and
	left for the reader to pick.
	"""
	tax_id = _digits(supplier.get("tax_id"))
	name = supplier.get("name") or ""
	if not tax_id and not name:
		return []

	found = []
	for row in frappe.get_list(
		SUPPLIER,
		fields=["name", "supplier_name", "tax_id"],
		filters={"disabled": 0},
		limit=SUPPLIER_ROWS,
	):
		if tax_id and _digits(row.tax_id) == tax_id:
			found.append((1.0, row, _("Same tax number, {0}").format(row.tax_id)))
			continue
		score = similarity(name, row.supplier_name or row.name)
		if score >= 0.95:
			found.append((score, row, _("Same name")))
		elif score >= SUPPLIER_OFFERED:
			found.append((score, row, _("Similar name")))

	found.sort(key=lambda match: match[0], reverse=True)
	return [
		{
			"name": row.name,
			"supplier_name": row.supplier_name,
			"tax_id": row.tax_id,
			"reason": reason,
			"strong": score >= SUPPLIER_CHOSEN,
		}
		for score, row, reason in found[:5]
	]


def _digits(value: str | None) -> str:
	"""A tax number without its spacing and punctuation, for comparing."""
	return re.sub(r"[^0-9A-Za-z]", "", value or "").upper()


def _words(value: str | None) -> list[str]:
	"""The words that say what a name or a line is.

	Bare numbers are left out along with the legal words: on these invoices they
	are mostly fiscal years, and "Statutory Audit 2081/82" is booked where
	"Statutory Audit 2080/81" was.
	"""
	words = re.sub(r"[^0-9a-z]+", " ", (value or "").lower()).split()
	return [word for word in words if word not in LEGAL_WORDS and not word.isdigit()]


def similarity(a: str | None, b: str | None) -> float:
	"""How alike two names or descriptions are, from 0 to 1.

	Compared without case, punctuation or legal suffixes, as the average of two
	measures. The characters in order catch spelling and spacing ("Pvt.Ltd"
	against "Pvt Ltd"). The words in common, counting a word misspelt by a
	letter as the same word, stop one long shared word from carrying the score:
	"Vianet Communications" and "Worldlink Communications" are alike character
	for character and are different suppliers.

	One more case lifts the score to 0.8: every word of the shorter name is in
	the longer one, as with "Vianet" against "Vianet Communications". That is
	below `SUPPLIER_CHOSEN`, because it is a reason to offer a supplier, not to
	choose it.
	"""
	left, right = _words(a), _words(b)
	if not left or not right:
		return 0.0
	characters = SequenceMatcher(None, " ".join(left), " ".join(right)).ratio()
	shared = sum(1 for word in set(left) if any(_same_word(word, other) for other in set(right)))
	words = shared / (len(set(left)) + len(set(right)) - shared)
	score = (characters + words) / 2
	shorter, longer = sorted((set(left), set(right)), key=len)
	if shorter <= longer and sum(len(word) for word in shorter) >= 6:
		score = max(score, 0.8)
	return score


def _same_word(a: str, b: str) -> bool:
	return a == b or (min(len(a), len(b)) >= 5 and SequenceMatcher(None, a, b).ratio() >= 0.85)


# --------------------------------------------------------------------------- #
# Accounts, taxes and duplicates, once the company and supplier are known      #
# --------------------------------------------------------------------------- #


@frappe.whitelist(methods=["POST"])
def suggest(
	company: str,
	descriptions: list[str],
	taxed: bool = False,
	supplier: str | None = None,
	bill_no: str | None = None,
) -> dict:
	"""What the draft should say for this company and supplier.

	`descriptions` are the lines as they stand, in order, and `lines` comes back
	in the same order. `taxed` is whether the scan shows any tax.
	"""
	_require()
	frappe.has_permission(COMPANY, "read", company, throw=True)
	default_account = frappe.db.get_value(COMPANY, company, "default_expense_account")

	history = [row for row in _history(company) if row.expense_account]
	from_supplier = [row for row in history if supplier and row.supplier == supplier]
	return {
		"lines": [
			_suggest_account(description, from_supplier, history, default_account)
			for description in descriptions
		],
		"taxes": _tax_options(company, supplier, taxed),
		"duplicates": _duplicates(supplier, bill_no),
		"currency": frappe.db.get_value(COMPANY, company, "default_currency"),
	}


def _history(company: str) -> list[dict]:
	"""This company's submitted invoice lines, newest first."""
	return frappe.get_list(
		PURCHASE_INVOICE,
		fields=[
			"name",
			"supplier",
			"items.item_name as item_name",
			"items.expense_account as expense_account",
		],
		filters={"company": company, "docstatus": 1},
		order_by="posting_date desc, creation desc",
		limit=HISTORY_ROWS,
	)


def _closest(description: str, rows: list[dict]) -> tuple[float, dict] | None:
	scored = [(similarity(description, row.item_name), row) for row in rows]
	return max(scored, key=lambda match: match[0], default=None)


def _suggest_account(description: str, from_supplier: list, history: list, default: str | None) -> dict:
	"""The account for one line, why, and whether the reader should look again.

	`review` is set only for the company default, which is a fallback rather
	than a suggestion.
	"""
	best = _closest(description, from_supplier)
	if best and best[0] >= SAME_SUPPLIER_LINE:
		row = best[1]
		return {
			"account": row.expense_account,
			"reason": _("As “{0}” from this supplier, on {1}").format(row.item_name, row.name),
			"review": False,
		}
	if from_supplier:
		account, count = Counter(row.expense_account for row in from_supplier).most_common(1)[0]
		return {
			"account": account,
			"reason": _("Where this supplier's lines usually go ({0} of {1})").format(
				count, len(from_supplier)
			),
			"review": False,
		}
	best = _closest(description, history)
	if best and best[0] >= ANY_LINE:
		row = best[1]
		return {
			"account": row.expense_account,
			"reason": _("As “{0}” on {1}").format(row.item_name, row.name),
			"review": False,
		}
	return {
		"account": default,
		"reason": _("The company's default expense account. Nothing like this has been booked before."),
		"review": True,
	}


def _tax_options(company: str, supplier: str | None, taxed: bool) -> dict:
	"""The ways this invoice could be taxed, and which one to start from.

	Each option is a `key` the draft sends back, which `_tax_rows` turns into
	rows on the server, so the rows themselves are never taken from the
	browser.
	"""
	options = [{"key": "none", "label": _("No taxes"), "summary": ""}]

	last = _last_taxed_invoice(company, supplier)
	if last:
		options.append(
			{
				"key": f"invoice:{last.name}",
				"label": _("As on {0}, this supplier's last invoice").format(last.name),
				"summary": _summarise(_rows_from_invoice(last)),
			}
		)

	templates = frappe.get_list(
		TAX_TEMPLATE,
		filters={"company": company, "disabled": 0},
		fields=["name", "is_default"],
		order_by="is_default desc, name asc",
	)
	for template in templates:
		options.append(
			{
				"key": f"template:{template.name}",
				"label": template.name + (_(" (default)") if template.is_default else ""),
				"summary": _summarise(_rows_from_template(template.name)),
			}
		)

	if not taxed:
		suggested, reason = "none", _("The scan shows no tax.")
	elif last:
		suggested, reason = f"invoice:{last.name}", _("How this supplier's last invoice was taxed")
	elif templates and (templates[0].is_default or len(templates) == 1):
		suggested, reason = f"template:{templates[0].name}", _("The company's tax template")
	elif templates:
		suggested, reason = "none", _("The scan shows tax. Choose which template applies.")
	else:
		suggested, reason = (
			"none",
			_("The scan shows tax, but this company has no tax template. Add the tax in the desk."),
		)
	return {"options": options, "suggested": suggested, "reason": reason}


def _last_taxed_invoice(company: str, supplier: str | None):
	"""This supplier's latest submitted invoice in this company, if it was taxed
	in a way that can be copied: `_rows_from_invoice` is empty otherwise."""
	if not supplier:
		return None
	names = frappe.get_list(
		PURCHASE_INVOICE,
		filters={"company": company, "supplier": supplier, "docstatus": 1},
		pluck="name",
		order_by="posting_date desc, creation desc",
		limit=1,
	)
	if not names:
		return None
	invoice = frappe.get_doc(PURCHASE_INVOICE, names[0])
	return invoice if _rows_from_invoice(invoice) else None


# The fields a tax row is copied with. Amounts are left out: ERPNext computes
# them from the rate on the new invoice.
TAX_FIELDS = (
	"category",
	"add_deduct_tax",
	"charge_type",
	"row_id",
	"account_head",
	"description",
	"rate",
	"cost_center",
	"included_in_print_rate",
)


def _rows_from_invoice(invoice) -> list[dict]:
	"""The tax rows of an earlier invoice, as rows for a new one.

	Fixed-amount (`Actual`) rows are left out, because last time's amount is not
	this time's. If that leaves a row computed from a row that is no longer
	there, the invoice cannot be copied at all, and nothing comes back.
	"""
	kept = [row for row in invoice.taxes if row.charge_type != "Actual"]
	if len(kept) != len(invoice.taxes) and any(row.charge_type.startswith("On Previous Row") for row in kept):
		return []
	return [{field: row.get(field) for field in TAX_FIELDS} for row in kept]


def _rows_from_template(name: str) -> list[dict]:
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	return get_taxes_and_charges(TAX_TEMPLATE, name) or []


def _summarise(rows: list[dict]) -> str:
	parts = []
	for row in rows:
		label = (row.get("description") or row.get("account_head") or "").strip()
		sign = "\u2212" if row.get("add_deduct_tax") == "Deduct" else ""
		rate = f"{flt(row.get('rate')):g}"
		# "VAT @ 13.0" already says it.
		stated = re.search(rf"\b{re.escape(rate)}(\.0+)?\b", label)
		parts.append(f"{label} {sign}{rate}%" if row.get("rate") and not stated else label)
	return " · ".join(parts)


def _tax_rows(key: str, company: str) -> tuple[str | None, list[dict]]:
	"""The template name and rows a tax option stands for, checked again here
	because the key came from the browser."""
	if not key or key == "none":
		return None, []
	kind, _separator, name = key.partition(":")
	if kind == "template":
		template = frappe.get_doc(TAX_TEMPLATE, name)
		template.check_permission("read")
		if template.company != company:
			frappe.throw(_("Tax template {0} belongs to {1}.").format(name, template.company))
		return name, _rows_from_template(name)
	if kind == "invoice":
		invoice = frappe.get_doc(PURCHASE_INVOICE, name)
		invoice.check_permission("read")
		if invoice.company != company:
			frappe.throw(_("Invoice {0} belongs to {1}.").format(name, invoice.company))
		template = invoice.taxes_and_charges
		return template or None, _rows_from_invoice(invoice)
	frappe.throw(_("Unknown tax option {0}.").format(key))


def _duplicates(supplier: str | None, bill_no: str | None) -> list[str]:
	"""Invoices already booked, or drafted, with this supplier's bill number."""
	bill_no = (bill_no or "").strip()
	if not supplier or not bill_no:
		return []
	return frappe.get_list(
		PURCHASE_INVOICE,
		filters={"supplier": supplier, "bill_no": bill_no, "docstatus": ["<", 2]},
		pluck="name",
	)


# --------------------------------------------------------------------------- #
# The draft                                                                    #
# --------------------------------------------------------------------------- #


def _build(invoice: dict, supplier_to_come: bool = False):
	"""The Purchase Invoice a draft stands for, computed but not inserted.

	Only the fields a person fills in on the desk form are taken from the
	draft: company, supplier, bill number and dates, the lines, the discount and
	which tax option. ERPNext settles everything else (payable account, cost
	centre, currency, exchange rate, totals) in `set_missing_values` and
	`calculate_taxes_and_totals`, the same as it does for the desk form.

	`supplier_to_come` is for a preview whose supplier the reader has asked to
	create, which does not exist yet. `set_missing_values` reads the party, so
	it is skipped, and the totals are computed in the company's currency. That
	is the currency a new supplier's invoice is in, since the supplier has no
	currency of its own.
	"""
	company = invoice.get("company")
	supplier = invoice.get("supplier")
	if not company:
		frappe.throw(_("Choose the company this invoice is billed to."))
	if not supplier and not supplier_to_come:
		frappe.throw(_("Choose the supplier."))

	lines = invoice.get("items") or []
	if not lines:
		frappe.throw(_("The invoice needs at least one line."))
	uom = frappe.db.get_single_value("Stock Settings", "stock_uom") or "Nos"
	items = []
	for index, line in enumerate(lines, start=1):
		description = (line.get("description") or "").strip()
		if not description:
			frappe.throw(_("Line {0} needs a description.").format(index))
		qty = flt(line.get("qty"))
		if qty <= 0:
			frappe.throw(_("Line {0} needs a quantity above zero.").format(index))
		if not line.get("expense_account"):
			frappe.throw(_("Choose an account for “{0}”.").format(description))
		items.append(
			{
				"item_name": description[:ITEM_NAME_LENGTH],
				"description": description,
				"qty": qty,
				"rate": flt(line.get("rate")),
				"uom": uom,
				"expense_account": line["expense_account"],
			}
		)

	template, taxes = _tax_rows(invoice.get("taxes") or "none", company)
	discount = flt(invoice.get("discount_amount"))
	bill_date = invoice.get("bill_date") or None
	document = frappe.get_doc(
		{
			"doctype": PURCHASE_INVOICE,
			"company": company,
			"supplier": supplier or None,
			# Dated as the invoice is unless the reader says otherwise, and
			# marked as set by hand, which is how nearly every invoice on this
			# site is booked.
			"posting_date": invoice.get("posting_date") or bill_date or today(),
			"set_posting_time": 1,
			"bill_no": (invoice.get("bill_no") or "").strip() or None,
			"bill_date": bill_date,
			"due_date": invoice.get("due_date") or None,
			"items": items,
			"taxes_and_charges": template,
			"taxes": taxes,
			"apply_discount_on": "Net Total" if discount else None,
			"discount_amount": discount,
		}
	)
	if supplier:
		document.set_missing_values()
	else:
		document.currency = frappe.get_cached_value(COMPANY, company, "default_currency")
		document.conversion_rate = 1
		for item in document.items:
			item.conversion_factor = 1
	document.calculate_taxes_and_totals()
	return document


@frappe.whitelist(methods=["POST"])
def preview(invoice: dict, new_supplier: bool = False) -> dict:
	"""ERPNext's totals for the draft, without saving anything.

	`new_supplier` says the draft's supplier is one `create` will make, so
	there is none to name yet.
	"""
	_require()
	document = _build(invoice, supplier_to_come=new_supplier)
	return {
		"currency": document.currency,
		"total": document.total,
		"net_total": document.net_total,
		"discount_amount": document.discount_amount,
		"taxes": [
			{
				"description": row.description,
				"amount": row.tax_amount_after_discount_amount
				* (-1 if row.add_deduct_tax == "Deduct" else 1),
			}
			for row in document.taxes
		],
		"total_taxes_and_charges": document.total_taxes_and_charges,
		"grand_total": document.grand_total,
		"rounded_total": None if document.disable_rounded_total else document.rounded_total,
	}


@frappe.whitelist(methods=["POST"])
def create(invoice: dict, new_supplier: dict | None = None) -> dict:
	"""Insert the draft, making the supplier first if the reader asked for one.

	One request, so one transaction: if the invoice is refused, a supplier
	made for it goes too, rather than staying behind with nothing booked
	against it.

	Inserted and not submitted. The scan is attached afterwards by the browser,
	through Frappe's upload, which checks write permission on the new invoice.
	"""
	_require()
	if new_supplier:
		invoice = {**invoice, "supplier": _new_supplier(new_supplier)}
	document = _build(invoice)
	document.insert()
	return {
		"name": document.name,
		"supplier": document.supplier,
		"grand_total": document.grand_total,
		"currency": document.currency,
	}


def _new_supplier(values: dict) -> str:
	name = (values.get("supplier_name") or "").strip()
	if not name:
		frappe.throw(_("Give the new supplier a name."))
	if frappe.db.exists(SUPPLIER, {"supplier_name": name}):
		frappe.throw(_("There is already a supplier called {0}. Choose it instead.").format(name))
	supplier = frappe.get_doc(
		{
			"doctype": SUPPLIER,
			"supplier_name": name,
			"supplier_type": "Company",
			"tax_id": (values.get("tax_id") or "").strip() or None,
		}
	)
	supplier.insert()
	return supplier.name
