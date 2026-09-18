# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Install/migrate hook for the core extensions: the two fields they read.

Neither correction this module makes could be a doctype of its own. Where the
Website button goes is a property of Website Settings, and which role's home page
wins is a property of a Role -- so each is a Custom Field on a core doctype,
created here on install and re-asserted on every migrate.

One entry point rather than two in `hooks.py`, so the hook lists read one line per
module the way `tbs_commons.requests.install` and
`tbs_commons.safer_permissions.install` do. The field definitions stay in the
modules that read them, next to the code that gives them meaning.
"""

from tbs_commons.commons_core import home_page, website_link


def sync_commons_core() -> None:
	"""Everything this module asserts on both install and migrate."""
	website_link.sync_website_button_field()
	home_page.sync_home_page_priority_field()
