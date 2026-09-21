"""Which of the apps this one can use are actually on this site.

This app requires nothing but Frappe. It *uses* ERPNext and HRMS where they are
there -- procurement spends against Companies and hands over to Material
Requests, leave and expenses are HRMS doctypes end to end -- and every one of
those features takes itself away where they are not. This module is the question
each of them asks first.

Two forms of it, and which one to ask is not a style choice.

`has_doctype` is the right question when the code touches a named doctype and
little else. `Leave Application` is the whole of the leave section; asking about
HRMS instead would be asking about the wrong thing, and would still be wrong on
a site that has HRMS but has somehow lost the doctype.

`installed` is the right question when a feature reaches across most of an app.
Procurement touches `Company`, `Department`, `Item`, `UOM`, `Stock Settings`,
`Fiscal Year`, `Material Request` and `Material Request Item`, plus three
functions imported from `erpnext` itself. Naming one of those as the test would
be picking a stand-in and pretending it meant the rest; naming all eight would
be a list to keep in step with the code. "Is ERPNext on this site" is the
question the code is actually asking.

Both are site-level and both are cheap. `frappe.get_installed_apps` is the
site's own list rather than the bench's -- an app can be on disk and not
installed here, and that is exactly the case this has to get right -- and the
doctype test is a cached lookup rather than a query.
"""

import frappe


def installed(app: str) -> bool:
	"""Whether `app` is installed on *this site*, not merely present on the bench."""
	return app in frappe.get_installed_apps()


def has_doctype(doctype: str) -> bool:
	"""Whether `doctype` exists on this site."""
	return bool(frappe.db.exists("DocType", doctype, cache=True))
