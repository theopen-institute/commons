"""App-level migrate hook: registering this app's modules.

Most of what this app adds to other apps' doctypes is declared rather than
created. The four Custom Fields it puts on Frappe's own doctypes are in
`commons/fixtures/custom_field.json`, written by Frappe's fixture sync on
install and every migrate; the desk icon is a file under `desktop_icon/`, written
by the model sync. Neither needs a hook. The hooks left in `hooks.py` do only
what no sync can: `commons.self_service.install` drops a cache whose key
`frappe.clear_cache` does not know about, `commons.safer_permissions.install`
gets a changed `page_js` in front of admins whose desks still hold the last copy
of it, and `commons.requests.install` writes the four fields that name ERPNext
doctypes -- which a fixture cannot, because ERPNext is optional and a fixture
that cannot resolve aborts migrate for the whole site rather than skipping
itself.

Workflows, self-service configuration and Property Setters are a System Manager's
to set up on a new site, and the app ships none of them -- not as a seed, not as
a fixture, not at all.

About that desk icon. It ships as a file in `commons/desktop_icon/`,
which `frappe.model.sync` imports on every migrate -- `desktop_icon` is one of its
`app_level_folders`. Keeping it as a record built at runtime meant migrate's orphan
sweep deleted it (it drops any `standard` icon with no backing file) and
`after_migrate` put it straight back, once per migrate.

`Commons Core` is the reason the function below is not merely a precaution. It
was a plain directory until `Commons Settings` moved into it, and a module that
gains its first doctype after the app is already installed somewhere is exactly
the case core's own `add_module_defs` does not cover: the record is written at
install and never again, so the doctype would name a module the site has never
heard of. That is what runs here, from `before_migrate`, ahead of the sync that
would trip over it.

Absorbing a retired app's modules
---------------------------------
`NepalERP` and `Education Extensions` are not this app's modules in any ordinary
sense. They are two a site filled in through the desk, under an app that is
being retired, and what is under them is the site's own: twenty-two Custom
DocTypes and several thousand rows of assessment, grading and financial-aid
history, plus the reports, print formats, scripts and workspaces that drive
them. See `commons.education_extensions` and `commons.nepalerp`.

They are here because of one line in `frappe.installer.remove_app`: it selects
what to delete with `Module Def` where `app_name` is the app being removed, and
then drops every doctype under those modules -- custom ones included, as its own
confirmation prompt warns -- along with every document linking to them.
Uninstalling NepalERP with those modules still pointing at it would take all of
it. Pointing `app_name` at this app instead empties that query, and nothing else
about the records changes.

`adopt` below does that, from the same `before_migrate` hook, so a site that
updates this app and migrates is absorbed without anyone running anything. It
is idempotent, it is a no-op on a site that never had the retired app, and it
takes a module only from the one app named in `ABSORBED_FROM` -- never from an
app that still wants it.

The other half is `modules.txt`, which has to name both, because that file is
what `frappe.setup_module_map` builds `module_app` from: `Workspace.validate`
sets `app` from `get_module_app(module)`, and a module no installed app claims
makes that throw. Naming them is also what puts
`commons/education_extensions/workspace/` on the sync's path, which is what
keeps those three workspaces alive past migrate's orphan sweep.

Which is why these two are *adopted* rather than created. `add_module_defs`
walks the whole of `modules.txt`, and left to it, every site running this app
would grow two empty modules named after somebody else's retired one.
"""

APP = "commons"

# Modules this app has taken over, and the app each was taken from. Adopted
# where the record already exists and created nowhere -- see above.
ABSORBED_FROM = {
	"NepalERP": "nepalerp",
	"Education Extensions": "nepalerp",
}


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

	frappe.cache.delete_value("app_modules")
	frappe.client_cache.delete_value("installed_app_modules")
	frappe.setup_module_map(include_all_apps=True)

	# `add_module_defs` in all but name, minus the absorbed modules -- see the
	# module docstring. Core's own version takes no filter, and the whole of it
	# is the loop below.
	for module in frappe.get_module_list(APP):
		if module in ABSORBED_FROM:
			continue
		record = frappe.new_doc("Module Def")
		record.app_name = APP
		record.module_name = module
		record.insert(ignore_permissions=True, ignore_if_duplicate=True)

	adopt()


def adopt() -> None:
	"""Take the retired app's modules over, so uninstalling it deletes nothing.

	One field on each record, and nothing else touched: the doctypes keep their
	module, the module keeps its name, and the site's own configuration under it
	is not read, let alone written. See the module docstring for why that one
	field is the whole of the job.

	Silent and idempotent. A site that never had the retired app has no such
	`Module Def` and nothing happens; a site already absorbed matches nothing to
	change. The `app_name` test is what keeps this narrow -- a module is taken
	only from the app it is named as belonging to, so this can never quietly
	claim one from an app that is still shipping it.
	"""
	import frappe

	for module, retired in ABSORBED_FROM.items():
		owner = frappe.db.get_value("Module Def", module, "app_name")
		if owner != retired:
			continue
		# `frappe.db.set_value`, not a document save: `app_name` is a Select
		# whose options core builds from the apps a site has, and nothing else
		# on the record is changing.
		frappe.db.set_value("Module Def", module, "app_name", APP)
		print(f"Module {module!r} absorbed from {retired!r} into {APP!r}")
