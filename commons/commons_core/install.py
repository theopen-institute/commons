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
the case core's own `add_module_defs` does not cover: `frappe.installer` calls
it from `install_app` and from nowhere else, so the record is written at install
and never again, and a module added to `modules.txt` afterwards would be named
by a doctype the site has never heard of. That is what runs here, from
`before_migrate`, ahead of the sync that would trip over it -- and it is a
standing need rather than a one-off, because the next module this app adds
meets the same gap on every site that already has the app.

`Education Extensions` is the same gap seen from the other end, and is why this
runs unfiltered. It is a module a site filled in through the desk under an app
since retired, and this app now ships the three workspaces under it as files --
so a site that gained the module on an upgrade rather than at install had those
workspaces naming a `Module Def` that was never written. There is no longer any
module here that is somebody else's: every name in `modules.txt` is one this app
answers for, and every one of them gets a record.

Why this is in `commons_core` and not at the app root
-----------------------------------------------------
It is the second of the two exceptions that module's own membership test admits,
and it is admitted on the same grounds as the first. `Commons Settings` is there
because a fact about *the app* belongs in the module named after the app; so is
this. Everything else under `commons_core` is an extension to Frappe and would
make sense in an app with none of this one's sections, which this would not.

The other direction
-------------------
`drop_stale_module_defs` is the second half, and it runs from `after_migrate`
rather than this one's `before_migrate`. Modules get renamed and merged --
`Auth0` and `Google Workspace` became `API Integrations` -- and core has no
notion of that at all, because `add_module_defs` runs at install, when there is
nothing yet to remove. Its own docstring argues the hook it is on.
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

	Migrate's own `setUp` calls `frappe.clear_cache()` before this hook, which
	drops both keys from `frappe.cache` -- but `installed_app_modules` is
	written through `frappe.client_cache`, whose local copy invalidates across
	processes on its own schedule rather than at once, and the rebuild is what
	puts the new module in front of the sync that follows in *this* process.
	Neither line is redundant with that call.
	"""
	import frappe

	frappe.cache.delete_value("app_modules")
	frappe.client_cache.delete_value("installed_app_modules")
	frappe.setup_module_map(include_all_apps=True)

	# `add_module_defs`, which core exposes only through `install_app`. The
	# whole of its body is the loop below, and this is it unfiltered: there is
	# no module in `modules.txt` this app does not answer for.
	for module in frappe.get_module_list(APP):
		record = frappe.new_doc("Module Def")
		record.app_name = APP
		record.module_name = module
		record.insert(ignore_permissions=True, ignore_if_duplicate=True)


def drop_stale_module_defs() -> None:
	"""Remove `Module Def` records for modules this app no longer has.

	The other half of `sync_module_defs`, and the one core has never needed:
	`add_module_defs` runs at install, when there is nothing to remove. A module
	that is renamed, merged into another or dropped outright leaves its record
	behind on every site that already had the app -- and a `Module Def` with
	nothing in it is not inert, it is a name in the doctype dropdown and an
	empty module in the desk's module list, for as long as nobody goes and
	deletes it by hand on each site.

	`API Integrations` is what made this a standing need rather than a tidy-up.
	`Auth0` was a module of its own before the integrations were gathered under
	one, so every site carrying this app has a record for a module that no
	longer exists.

	Deliberately in `after_migrate` while its counterpart is in
	`before_migrate`. Addition has to happen before the doctype sync, or the
	sync cannot import a doctype naming a module the site has never heard of.
	Removal has to happen after it, because until the sync has run the doctype
	still names the *old* module -- so a removal running first would find the
	record still in use, skip it, and leave the site needing a second migrate to
	converge. That is the shape this module's own docstring complains about
	elsewhere, and it is avoidable here by picking the right hook.

	`app_name` is the guard that keeps this to this app's own records: another
	app's modules are not this one's to reconcile, and neither are the ones a
	site made by hand.

	`LinkExistsError` is the other guard, and it is the one that matters. A
	module is still named by anything that lives in it -- a doctype, a report, a
	page, a workspace -- and Frappe's own link check is a better answer to
	"is this really unused" than any list of tables that would have to be kept
	up to date here. Something still pointing at it means it is not stale, so it
	is left exactly where it is rather than removed with a flag that would
	silently break whatever was pointing.
	"""
	import frappe

	current = set(frappe.get_module_list(APP))
	for name in frappe.get_all("Module Def", filters={"app_name": APP}, pluck="name"):
		if name in current:
			continue
		try:
			frappe.delete_doc("Module Def", name, ignore_permissions=True)
		except frappe.LinkExistsError:
			# Still in use, so not stale. Left alone, and reconsidered on the
			# next migrate once whatever names it has moved or gone.
			pass
