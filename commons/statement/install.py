"""Install and migrate hook for the statement section: its print formats.

One `Print Format` per party doctype the site actually has, because a print
format is attached to exactly one doctype and a statement can be printed for a
Customer, a Student, a Supplier or an Employee.

Written from a hook rather than shipped as files, and the reason is the one
`commons.requests.install` sets out at length: every doctype named here belongs
to another app and every one of them is optional. `Customer` and `Supplier`
arrive with ERPNext, `Student` with Education, and a site may have none of them.
A standard print format shipped as a file would be imported on every site
whatever it named -- Frappe's import sets `ignore_links`, so it would not fail,
which is worse than failing: every site would grow a print format attached to a
doctype it does not have, offered in lists and printing nothing.

So the rule is the same one that module uses: assert what this site can hold,
and be silent about the rest.

Created, not maintained
-----------------------

A format that already exists is left exactly as it is. That is deliberate and it
costs nothing, because the record is a two-line stub:

    {% set statement = party_statement(doc.doctype, doc.name) %}
    {% include "commons/statement/print/statement.html" %}

Everything that could need changing -- the layout, the wording, the figures --
is behind that include or behind that call, and both are files this app ships
and migrate updates. So an administrator who restyles the stub keeps their
restyling, and still gets every later change to the statement itself. That is
the opposite way round from most generated configuration, and it is only
possible because the generated part is two lines.

`standard` is `No` for the same reason. A standard print format cannot be edited
outside developer mode, and `PrintFormat.on_update` writes standard formats back
out to the app's own directory -- neither of which is wanted for a record this
app creates on somebody else's site.
"""

import frappe

from commons.commons_core import apps
from commons.statement import print_format_name
from commons.statement.parties import PARTY_TYPE, USER_LINKS

# This app's own module, so the print formats are grouped with the code that
# renders them rather than filed under whichever app owns the party doctype.
MODULE = "Statement"

# The whole of what a generated format contains. `doc` is the party document the
# format is attached to, and naming it by `doc.doctype` rather than by the party
# type this record was created for means the same two lines are correct on all
# four -- and stay correct if somebody points the format at another doctype.
STUB = """{%- set statement = party_statement(doc.doctype, doc.name) -%}
{% include "commons/statement/print/statement.html" %}
"""


def sync_statement_print_formats() -> None:
	"""Create a statement print format for each party type this site has.

	Silent on a site with none, and silent about a format that is already there.
	Neither is a degraded install: without ERPNext there is no ledger to print
	from and the section has already taken itself off the navigation -- see
	`ledger.available`.
	"""
	if not apps.has_doctype(PARTY_TYPE) or not apps.has_doctype("Print Format"):
		return

	for party_type in USER_LINKS:
		# Both questions, because they are different ones. The doctype can be
		# here without being a party type -- `Employee` is on every site with
		# HRMS, and it is only a party where somebody has said so -- and a
		# statement for a doctype that is not a party type would have no
		# `account_type` to read a balance against.
		if not apps.has_doctype(party_type) or not frappe.db.exists(PARTY_TYPE, party_type):
			continue
		_create(party_type)


def _create(party_type: str) -> None:
	"""One print format, if this site has not got one already."""
	name = print_format_name(party_type)
	if frappe.db.exists("Print Format", name):
		return

	frappe.get_doc(
		{
			"doctype": "Print Format",
			"name": name,
			"doc_type": party_type,
			"module": MODULE,
			"print_format_type": "Jinja",
			# The format supplies its own template rather than being laid out
			# field by field from the doctype -- which is the whole point, since
			# none of what it prints is on the document.
			"custom_format": 1,
			"standard": "No",
			"html": STUB,
		}
	).insert(ignore_permissions=True)
