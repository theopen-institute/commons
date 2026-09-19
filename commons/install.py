"""App-level migrate hook: registering this app's modules.

Everything else this app adds to core and ERPNext doctypes is declared rather
than created. The nine Custom Fields are in
`commons/fixtures/custom_field.json`, written by Frappe's fixture sync on
install and every migrate; the desk icon is a file under `desktop_icon/`, written
by the model sync. Neither needs a hook. The two hooks left in `hooks.py` do only
what no sync can: `commons.self_service.install` drops a cache whose key
`frappe.clear_cache` does not know about, and
`commons.safer_permissions.install` gets a changed `page_js` in front of
admins whose desks still hold the last copy of it.

Workflows, self-service configuration and Property Setters are a System Manager's
to set up on a new site, and the app ships none of them -- not as a seed, not as
a fixture, not at all.

About that desk icon. It ships as a file in `commons/desktop_icon/`,
which `frappe.model.sync` imports on every migrate -- `desktop_icon` is one of its
`app_level_folders`. Keeping it as a record built at runtime meant migrate's orphan
sweep deleted it (it drops any `standard` icon with no backing file) and
`after_migrate` put it straight back, once per migrate.

`core` is a directory and not a line in `modules.txt`, so nothing here is
about it: a module earns a `Module Def` by owning desk artifacts, and that one
owns none. Its own `__init__.py` says what would change if it grew some -- the
function below is most of the answer, because it is what lets a module be added
to an app that is already installed somewhere.
"""

APP = "commons"


def sync_module_defs() -> None:
	"""Register this app's modules before migrate imports doctypes into them.

	`Module Def` records are created by `add_module_defs` when an app is
	*installed* and never again, so a module added to `modules.txt` afterwards
	has none -- and importing a doctype that names it fails. This runs from
	`before_migrate`, ahead of the doctype sync that would trip over it.

	The record is only half of it. Which modules an app has is itself cached --
	`frappe.setup_module_map` keeps the whole bench's map under `app_modules`,
	and the site's own under `installed_app_modules` -- and the doctype sync
	walks that map rather than the file. A module added to `modules.txt` and
	left to the cache is therefore not merely unregistered: its `doctype/`
	folder is not looked in at all, and the first migrate after the upgrade
	syncs everything except the new module, silently, with a second migrate
	putting it right. Dropping both keys and rebuilding the map here is what
	makes the first one enough.
	"""
	import frappe
	from frappe.installer import add_module_defs

	frappe.cache.delete_value("app_modules")
	frappe.client_cache.delete_value("installed_app_modules")
	frappe.setup_module_map(include_all_apps=True)

	add_module_defs(APP, ignore_if_duplicate=True)
