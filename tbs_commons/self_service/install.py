"""Migrate hook for the self-service section: dropping the resolved registry.

Everything this section needs in order to *work* is in its own doctype
definitions, which migrate imports on its own. What it needs in order to be
useful -- which record types are self-service, which fields staff may propose
corrections to, and who decides a proposal -- is configuration, held as
`Self Service Record` documents and a `Workflow` that a site owns. The app writes
none of it and carries none of it: a System Manager sets it up on a new site, and
`tbs_commons.self_service.registry` reads whatever they set up. A site with no
configuration is a coherent site -- nothing is self-service -- rather than a
broken one.

What is left is a cache. The registry resolved from those documents is cached
across requests and keyed by nothing that changes on deploy, so a migrate that
alters the shape the registry reads -- a new field in its query, a new column on
the configuration -- would otherwise keep answering from the old one until
something happened to clear it. `frappe.clear_cache` does not know about this
key. Saving or deleting a `Self Service Record` clears it on its own, so this is
only about the deploy.
"""

from tbs_commons.self_service import registry


def sync_self_service() -> None:
	"""Everything the self-service section asserts on both install and migrate."""
	registry.clear_cache()
