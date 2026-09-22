"""Telling this app's two kinds of test apart, so the wrong runner says so quietly.

This app has site-less unit tests and site-connected integration suites, and the
split is deliberate: the suites that exercise a real Workflow, real permissions
and a real document round trip would be worth nothing mocked -- see
`commons.self_service.test_record_change`, which says so at length. Each of them
names its own runner on its first line.

What this module is for is the person who does not read that first line.
`python -m unittest discover` over the app collects everything, the integration
suites reach for `frappe.db` against no site, and the result is a hundred errors
that look exactly like a broken app and are not. The signal that matters -- did
the site-less tests pass -- is buried under them.

So the suites that need a site say so, with `site_suite`, and site-less
discovery reports them as skipped rather than failed. Nothing changes for the
runners that do connect: the condition is true, the decorator does nothing, and
the suite runs as it always has.

Where a skip has to be decided at import
-----------------------------------------
`unittest.skipUnless` takes a value, not a callable, so its condition runs while
the module is being imported -- before any runner has had a chance to skip
anything. A condition that reads the database is therefore not a skip at all: it
is an `ImportError` that takes the whole module with it, which is what
`commons.requests.test_approvers` used to do. `has_doctype` is the same question
asked safely, answering `False` where there is no site to ask.
"""

import unittest

import frappe

# What a site-less runner is told. One sentence, and it names the way out.
NO_SITE = "needs a site: run it with bench (see this module's first line)"


def connected() -> bool:
	"""Whether there is a database to test against.

	`frappe.db` is a proxy that exists whether or not anything is behind it, so
	this asks the proxy rather than comparing it to `None` -- site-less it is
	falsy, and under a site it is the connection. The `RuntimeError` is the
	proxy's own way of saying nothing is bound, raised by some versions where
	others answer falsy; both readings are the same answer.
	"""
	try:
		return bool(frappe.db)
	except RuntimeError:
		return False


def site_suite(reason: str = NO_SITE):
	"""Class decorator: skip this suite where there is no site to run it against.

	A skip and not a failure, because a suite that cannot run is not a suite
	that failed, and the difference is the whole point -- a site-less sweep
	should end green when the site-less tests pass.
	"""
	return unittest.skipUnless(connected(), reason)


def has_doctype(doctype: str) -> bool:
	"""Whether this site has `doctype`, answered safely with no site at all.

	`commons.commons_core.apps.has_doctype` for application code, which runs
	under a site by definition and should not be made to look as though it might
	not. This one is for a skip condition, which runs at import -- see the
	module docstring.
	"""
	return connected() and bool(frappe.db.exists("DocType", doctype, cache=True))
