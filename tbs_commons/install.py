"""App-level migrate hook: registering this app's modules.

Everything else an install or migrate asserts belongs to one section and is
wired into `hooks.py` from that section -- `tbs_commons.requests.install` for
the Custom Fields and the Workflow, `tbs_commons.safer_permissions.install` for
the gate column, `tbs_commons.commons_core.install` for the two fields the core
extensions read.

The desk icon is in none of them. It ships as a file in `tbs_commons/desktop_icon/`,
which `frappe.model.sync` imports on every migrate -- `desktop_icon` is one of its
`app_level_folders`. Keeping it as a record built at runtime meant migrate's orphan
sweep deleted it (it drops any `standard` icon with no backing file) and
`after_migrate` put it straight back, once per migrate.

`commons_core` is a directory and not a line in `modules.txt`, so nothing here is
about it: a module earns a `Module Def` by owning desk artifacts, and that one
owns none. Its own `__init__.py` says what would change if it grew some -- the
function below is most of the answer, because it is what lets a module be added
to an app that is already installed somewhere.
"""

APP = "tbs_commons"


def sync_module_defs() -> None:
	"""Register this app's modules before migrate imports doctypes into them.

	`Module Def` records are created by `add_module_defs` when an app is
	*installed* and never again, so a module added to `modules.txt` afterwards
	has none -- and importing a doctype that names it fails. This runs from
	`before_migrate`, ahead of the doctype sync that would trip over it.
	"""
	from frappe.installer import add_module_defs

	add_module_defs(APP, ignore_if_duplicate=True)
