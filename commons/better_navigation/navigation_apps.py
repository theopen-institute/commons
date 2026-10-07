"""The rail: which apps it lists, and which modules each one offers.

Three levels, in this app's terms rather than Frappe's:

    Navigation App   an entry on the rail
      Module         a Module Def, as Frappe 16.50 shows it: its `Sidebar`
        Item         a row in that sidebar (a `Sidebar Item`)

Only the top level is this app's. The bottom two are Frappe's own: since 16.50
every module has a sidebar (shipped, made on the site, or worked out from what
the module holds), resolved per user into `frappe.boot.module_sidebars` with
the site's and the user's Custom Sidebar layers applied. That is also where a
site overrides a module -- relabel it, change its icon, add or hide its rows --
and a custom Module Def is a synthetic module. This adds the level above, which
Frappe has only for installed apps: its Dock lists the open app's modules, and
its Apps screen lists installed apps, neither of which a site can regroup.

"App" here is not an installed app. A `Navigation App` is whatever grouping a
site wants on its rail -- "Finance" holding modules from ERPNext and from this
app, say -- and a site may add as many as it likes.

One can also stand for an installed app, or for "Other", by naming it in
`installed_app`. It then takes that app's place on the rail rather than
appearing beside it: in its own Rail Order, under its own title, roles and
mark, falling back to the app's hooks for the logo and the frontend. Its
modules table either adds to what the app already holds (and relabels
anything it lists) or, set to Replace, is the whole list, and what the app
would have held goes to Other. The table's row order is the order the rail
lists them in; only what nobody has put in order is sorted, landing module
first (see `_default_order`). The table can also hold Category rows, a heading
over the modules after it, and Spacer rows, a gap; see `_layout`. Hidden takes it off the rail, and its modules
with it. "Other" is bindable like any installed app: the one group no hooks
describe, but as much the site's to rename, restrict or hide.

The fallback is the installed apps
----------------------------------
A site that has configured nothing still gets a rail: one entry per installed
app, holding the modules that belong to it. And a site that has configured some
apps loses nothing it did not mention -- every module no `Navigation App`
claims is still grouped under its installed app, after the configured ones. So
installing an app puts it on the rail without anybody touching this, and
configuring is only ever a matter of claiming what should move.

Which installed app a module belongs to is Frappe's answer, already in the
boot: each `module_sidebars` entry's `app` (its sidebar's own, else where the
module is placed -- `modules.txt`, or a custom module's `app_name`), with the
Module Def's `app_name` as the fallback. A companion app's modules go to the
app Frappe mounts it on (`app_hosts`). A module neither places is grouped
under "Other", which is the honest answer and a hint that it wants an app or
claiming.

A module is one or more shells in the boot: usually one sidebar named after
it, but a renamed sidebar keeps its own name (ERPNext's "Quality" is module
"Quality Management") and a module may have two. A row claims the module, so
it claims all of them.

Two rules
---------
*A module is in one app.* The header has to say which app and module the page
you are on belongs to, and a module in two apps has no answer. Enforced when a
`Navigation App` is saved; here the first to claim one keeps it, so a conflict
that got past the form still resolves the same way every time.

*A role-restricted app still claims its modules.* Otherwise somebody without
the role would find the same modules back under their installed app, and the
restriction would only have moved them. Roles decide who sees the app on the
rail; they are not permission. A module a person cannot open is not in their
`module_sidebars` to begin with.
"""

import frappe
from frappe import _

APP = "Navigation App"
APP_SIDEBAR = "Navigation App Sidebar"

# Where a module goes when nothing says which app it belongs to.
OTHER = "Other"
OTHER_LOGO = "/assets/commons/images/commons-other-logo.svg"

# A Navigation App bound to an installed app either adds its modules table to
# what the app already holds, or replaces it.
ADD = "Add"
REPLACE = "Replace"

# What a row of a Navigation App's modules table is. Anything else -- unset, or
# "Sidebar" from before rows named modules -- is a module.
MODULE = "Module"
CATEGORY = "Category"
SPACER = "Spacer"

# The module an app starts from, when its name does not say so already.
HOME = "home"


# The site-level half of the rail: everything `resolve` reads except the user.
CACHE_KEY = "commons_navigation_rail"


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Hand the desk its rail, when the rail is switched on.

	On the boot rather than behind a call, so the rail draws with the sidebar
	instead of after it. Left off entirely while the switch is off: the rail's
	script checks the same flag and installs nothing.

	Runs after Frappe has built `module_sidebars` for this user, and reads the
	modules from there, so the rail offers exactly what the desk would. The boot
	is otherwise left as Frappe made it: which rail app each module is in is
	written into the desk's copy by the browser (`js/boot_arrangement.js`),
	which can write it again whenever Frappe replaces that copy.
	"""
	from commons.commons_core import settings

	if not settings.feature_enabled(settings.ENABLE_NAVIGATION_RAIL):
		return
	module_sidebars = bootinfo.get("module_sidebars")
	if module_sidebars is None:
		return
	try:
		bootinfo.navigation_apps = navigation_apps(module_sidebars=module_sidebars)
	except Exception:
		# The boot is every page load: a broken rail must not take the desk with it.
		# Without `navigation_apps` the browser half installs nothing.
		frappe.log_error(title="Navigation rail: kept Frappe's Dock", defer_insert=True)


def navigation_apps(
	user: str | None = None, module_sidebars: dict | None = None, everything: bool = False
) -> list[dict]:
	"""The rail for `user` (the session user by default), read from the site.

	`module_sidebars` is the boot's, when there is a boot; otherwise Frappe
	builds it again for the session user.
	"""
	user = user or frappe.session.user
	if module_sidebars is None:
		from frappe.boot import get_module_sidebars

		module_sidebars = get_module_sidebars()
	return resolve(
		**_site_inputs(),
		sidebars=_shells(module_sidebars),
		hosts=app_hosts(),
		user=user,
		user_roles=set(frappe.get_roles(user)),
		everything=everything,
	)


def app_hosts() -> dict[str, str]:
	"""Each companion app and the installed app whose rail it mounts on.

	Frappe shows a companion's modules (India Compliance's, say) as its host's
	(ERPNext's), so the rail groups them there too. Frappe's answer, asked per
	request: it changes with the site's Dock records, which this does not watch.
	"""
	try:
		from frappe.boot import get_app_rail_host_map
	except ImportError:
		return {}
	return get_app_rail_host_map() or {}


def _site_inputs() -> dict:
	"""What the rail is built from that is the same for everyone, cached.

	Seven queries and a hooks read per desk load otherwise, for data that
	changes when an administrator edits the rail or installs an app. Kept in
	`frappe.client_cache` (process-local, invalidated through redis) and dropped
	by `clear_cache`, which the doc events on everything read here call. An app
	installed, removed or migrated needs no call: `install_app`, `remove_app`
	and migrate each run `frappe.clear_cache()`, which drops every key the site
	has.
	"""
	return frappe.client_cache.get_value(
		CACHE_KEY,
		generator=lambda: {
			"configured": _configured(),
			"installed_apps": frappe.get_installed_apps(),
			"app_meta": _app_meta(),
			"module_apps": dict(frappe.get_all("Module Def", fields=["name", "app_name"], as_list=True)),
			"frontends": _frontends(),
		},
	)


def clear_cache(*args, **kwargs) -> None:
	"""Forget the rail's site-level inputs: now, and again when this transaction ends.

	A doc event, so it takes the hook's arguments. Again at the end for the reason
	`commons.derived_docfields.registry.clear` gives: a read in between would put
	back a copy right for only one of commit and rollback.
	"""
	frappe.client_cache.delete_value(CACHE_KEY)
	if db := getattr(frappe.local, "db", None):
		db.after_commit.add(_forget)
		db.after_rollback.add(_forget)


def _forget() -> None:
	frappe.client_cache.delete_value(CACHE_KEY)


def resolve(
	*,
	configured: list[dict],
	sidebars: list[dict],
	installed_apps: list[str],
	app_meta: dict[str, dict],
	module_apps: dict[str, str],
	user: str,
	user_roles: set[str],
	frontends: dict[str, str] | None = None,
	hosts: dict[str, str] | None = None,
	everything: bool = False,
) -> list[dict]:
	"""The rail, from plain data: configured apps first, then the installed ones.

	`configured` is the enabled Navigation Apps in rail order, each with its
	`sidebars` rows (`type`, `module`, `label`), `roles`, and optionally the
	`installed_app` it stands for, its `sidebar_mode`, whether it is `hidden`
	and its `apps_screen`.
	`sidebars` is the shells this user may open, from `module_sidebars`
	(`name`, `module`, `app`, `label`, `header_icon`; see `_shells`). The rest
	say what an installed app is called and which app a module belongs to,
	`frontends` where an installed app's own frontend is, outside the desk, and
	`hosts` which installed app a companion app mounts on (see `app_hosts`).

	Every entry carries `frontend` -- `{label, url}` or None -- beside its
	`sidebars`, which are modules only, one per shell: a module may carry a
	`category` or `space_before` to draw above it (see `_layout`). An app is on
	the rail if it has either: a frontend with no desk modules (Frappe Builder,
	say) is somewhere to go too. `app_name` is the name the desk's boot knows it
	by (`js/boot_arrangement.js`); a configured entry also names its `record`.

	`everything` is the rail as an editor needs it (`arrange.py`): hidden and
	role-restricted apps stay in, at their place, marked `hidden`, and so do
	apps with nothing to offer.
	"""
	frontends = frontends or {}
	hosts = hosts or {}
	by_module: dict[str, list[dict]] = {}
	for sidebar in sidebars:
		by_module.setdefault(sidebar.get("module") or sidebar["name"], []).append(sidebar)
	claimed: set[str] = set()

	# Claims first, all of them, so what is left for the installed apps is known
	# before any entry is drawn: a bound app early on the rail still gets the
	# modules no later app claims.
	claims: list[list[dict]] = []
	for app in configured:
		entries = []
		for row in app["sidebars"]:
			if row_type(row) != MODULE:
				entries.append(_marker(row))
				continue
			shells = [s for s in by_module.get(row.get("module") or "", []) if s["name"] not in claimed]
			# Gone since, out of this user's reach, or already claimed by an
			# earlier app. A module of two shells keeps their own labels.
			for sidebar in shells:
				claimed.add(sidebar["name"])
				label = row.get("label") if len(shells) == 1 else None
				entries.append(_entry(sidebar, label, row.get("desktop_image")))
		claims.append(entries)

	grouped: dict[str, list[dict]] = {}
	for sidebar in sidebars:
		if sidebar["name"] in claimed:
			continue
		owner = default_app_of(sidebar.get("app"), sidebar.get("module"), module_apps, hosts, installed_apps)
		grouped.setdefault(owner, []).append(_entry(sidebar))

	# Which configured app stands for which installed app: the first enabled one
	# to name it, as with claims. A later one naming the same app is only a
	# grouping of its own.
	bound: dict[str, int] = {}
	for index, app in enumerate(configured):
		target = app.get("installed_app")
		if target and target not in bound and (target in installed_apps or target == OTHER):
			bound[target] = index

	# Replacing drops what the app would have held into Other, where every
	# sidebar nothing places goes -- unless it is Other that replaces, when
	# there is nowhere further for them to go.
	for target, index in bound.items():
		if configured[index].get("sidebar_mode") == REPLACE and target != OTHER:
			grouped.setdefault(OTHER, []).extend(grouped.pop(target, []))

	rail: list[dict] = []
	for index, app in enumerate(configured):
		target = next((t for t, i in bound.items() if i == index), None)
		meta = app_meta.get(target) or {}
		# Listed rows in the table's order, then (Add) what the app already held,
		# in the default order.
		entries = list(claims[index])
		if target and app.get("sidebar_mode") != REPLACE:
			names = {app["title"], meta.get("title") or target, target}
			entries += _default_order(grouped.get(target) or [], names)
		entries = _layout(entries)

		# Hidden, or restricted to roles this user lacks: off the rail, and what it
		# holds goes with it rather than back to an installed app.
		roles = set(app.get("roles") or ())
		if not everything:
			if app.get("hidden"):
				continue
			if roles and not roles & user_roles:
				continue

		own_mark = app.get("logo") or app.get("icon")
		frontend = _frontend(
			app["title"],
			app.get("frontend_url") or (frontends.get(target) if target else None),
			app.get("frontend_label"),
		)
		if entries or frontend or everything:
			rail.append(
				{
					# A bound app keeps its installed app's key: the browser finds an
					# app by it and remembers each app's last module under it.
					"key": f"app:{target}" if target else f"navigation-app:{app['name']}",
					"app_name": _app_name(target) if target else f"navigation-app:{app['name']}",
					"record": app["name"],
					"installed_app": target,
					**({"hidden": bool(app.get("hidden")), "roles": sorted(roles)} if everything else {}),
					"title": app["title"],
					"icon": app.get("icon") or None,
					"logo": app.get("logo") or (None if own_mark else _default_logo(target, meta)),
					"configured": True,
					"sidebars": entries,
					"frontend": frontend,
					# How the Apps screen shows it; see `apps_screen.py`.
					"apps_screen": app.get("apps_screen") or None,
				}
			)

	for app_name in [*installed_apps, OTHER]:
		if app_name in bound:
			continue
		entries = grouped.get(app_name) or []
		meta = app_meta.get(app_name) or {}
		title = meta.get("title") or (OTHER if app_name == OTHER else app_name)
		frontend = _frontend(title, frontends.get(app_name))
		if not entries and not frontend and not everything:
			continue
		rail.append(
			{
				"key": f"app:{app_name}",
				"app_name": _app_name(app_name),
				"installed_app": app_name,
				**({"hidden": False, "roles": []} if everything else {}),
				"title": title,
				"icon": None,
				"logo": _default_logo(app_name, meta),
				"configured": False,
				"sidebars": _default_order(entries, {title, app_name}),
				"frontend": frontend,
			}
		)
	return rail


def _app_name(app_name: str) -> str:
	"""The name Frappe's boot knows a rail app by: the installed app's own, or one for Other."""
	return "commons-other" if app_name == OTHER else app_name


def _default_logo(app_name: str | None, meta: dict) -> str | None:
	"""An installed app's logo from its hooks, or Other's own."""
	return meta.get("logo") or (OTHER_LOGO if app_name == OTHER else None)


def _frontend(app_title: str, url: str | None, label: str | None = None) -> dict | None:
	"""An app's own frontend as the menus offer it, or None if it has none."""
	url = (url or "").strip()
	if not url:
		return None
	return {"label": (label or "").strip() or _("{0} app").format(app_title), "url": url}


def is_desk_route(url: str) -> bool:
	"""Whether a link leads into the desk rather than out of it.

	Several apps point their apps screen entry at a desk page (Frappe HR at
	`/desk/people`, Lending at `/app/lending`); that is the app's desk home, which
	its sidebars already reach, not a frontend of its own.
	"""
	path = (url or "").strip().split("?")[0].split("#")[0].rstrip("/")
	return path in ("/app", "/desk") or path.startswith(("/app/", "/desk/"))


def installed_app_of(sidebar: dict, module_apps: dict[str, str]) -> str | None:
	"""Which installed app a module belongs to, asked in the order the module docstring gives."""
	if sidebar.get("app"):
		return sidebar["app"]
	module = (sidebar.get("module") or "").strip()
	return module_apps.get(module)


def default_app_of(
	app: str | None,
	module: str | None,
	module_apps: dict[str, str],
	hosts: dict[str, str],
	installed_apps,
) -> str:
	"""The installed app a module is grouped under when no Navigation App claims it, or Other.

	A companion app's module goes to the app it mounts on, as Frappe's desk shows it.
	"""
	owner = installed_app_of({"app": app, "module": module}, module_apps)
	owner = hosts.get(owner, owner)
	return owner if owner in installed_apps else OTHER


def _default_order(entries: list[dict], app_names: set[str]) -> list[dict]:
	"""Modules nobody has put in order: the app's landing module, then the rest.

	Modules have no order of their own across an app (a Dock is an order only
	for the apps that ship one). So alphabetical, by what
	the menus call them -- except that a module called "Home", or called what
	the app is (Education's "Education", Lending's "Lending"), is where the app
	starts, and goes first. Home before the app-named one if an app has both.
	A Navigation App's sidebars table is an order someone chose, and is never
	passed through this.
	"""
	names = {name.casefold() for name in app_names if name}

	def rank(entry: dict) -> tuple[int, str]:
		keys = {entry["sidebar"].casefold(), entry["label"].casefold()}
		landing = 0 if HOME in keys else 1 if keys & names else 2
		return landing, entry["label"].casefold()

	return sorted(entries, key=rank)


def row_type(row) -> str:
	"""What a sidebars table row is; anything unknown or unset is a module."""
	kind = row.get("type")
	return kind if kind in (CATEGORY, SPACER) else MODULE


def _marker(row: dict) -> dict:
	"""A Category or Spacer row, as `_layout` reads it. A Category with no label is a Spacer."""
	label = (row.get("label") or "").strip()
	if row_type(row) == CATEGORY and label:
		return {"category": label}
	return {"space_before": True}


def _layout(rows: list[dict]) -> list[dict]:
	"""Modules only, each Category or Spacer moved onto the module that follows it.

	So everything that counts or picks modules -- the "N modules" subtitle, the
	landing module, the last one opened -- sees modules and nothing else, and a
	browser that drops a module this user cannot open moves what was above it
	on to the next (the rail does the same).

	A Category ends whatever came before it, so a Spacer just before or just
	after one adds nothing. One with no module after it in the table heads what
	the app holds besides (Add mode), and with nothing there either is dropped,
	as is a Category whose modules are all gone. A gap over the first module is
	dropped too: there is nothing above it to keep apart from.
	"""
	laid_out: list[dict] = []
	pending: dict = {}
	for row in rows:
		if "sidebar" not in row:
			if "category" in row or "category" not in pending:
				pending = dict(row)
			continue
		laid_out.append({**row, **pending})
		pending = {}
	if laid_out:
		laid_out[0].pop("space_before", None)
	return laid_out


def _entry(sidebar: dict, label: str | None = None, desktop_image: str | None = None) -> dict:
	entry = {
		"sidebar": sidebar["name"],
		"label": (label or "").strip() or sidebar.get("label") or sidebar["name"],
		"icon": sidebar.get("header_icon") or None,
	}
	# Only the Apps screen draws it (`apps_screen.py`), so it is carried only
	# when a row sets one.
	if desktop_image:
		entry["desktop_image"] = desktop_image
	return entry


def _configured() -> list[dict]:
	apps = frappe.get_all(
		APP,
		filters={"enabled": 1},
		fields=[
			"name",
			"title",
			"icon",
			"logo",
			"frontend_url",
			"frontend_label",
			"installed_app",
			"sidebar_mode",
			"hidden",
			"apps_screen",
		],
		order_by="rail_order asc, title asc",
	)
	if not apps:
		return []

	names = [app.name for app in apps]
	rows = frappe.get_all(
		APP_SIDEBAR,
		filters={"parent": ["in", names], "parenttype": APP},
		fields=["parent", "type", "module", "label", "desktop_image"],
		order_by="parent asc, idx asc",
		parent_doctype=APP,
	)
	roles = frappe.get_all(
		"Has Role",
		filters={"parent": ["in", names], "parenttype": APP},
		fields=["parent", "role"],
		parent_doctype=APP,
	)

	for app in apps:
		app["sidebars"] = [row for row in rows if row.parent == app.name]
		app["roles"] = [row.role for row in roles if row.parent == app.name]
	return apps


def _shells(module_sidebars: dict) -> list[dict]:
	"""The shells in Frappe's `module_sidebars`, as `resolve` reads them, in the boot's order."""
	return [
		{
			"name": name,
			"module": sidebar.get("module") or name,
			"app": sidebar.get("app"),
			"label": sidebar.get("label") or name,
			"header_icon": sidebar.get("header_icon"),
		}
		for name, sidebar in module_sidebars.items()
	]


def _frontends() -> dict[str, str]:
	"""Each installed app's own frontend, outside the desk, as its hooks declare it.

	The apps screen's `route` (`add_to_apps_screen`), the hook the title and logo
	already come from. Code, not site data, so the rail describes an installed
	app the same way on every site; a site that wants a different link sets it
	on a Navigation App. Routes that only open a desk page are not frontends.
	"""
	found: dict[str, str] = {}
	for app_name in frappe.get_installed_apps():
		screen = (frappe.get_hooks("add_to_apps_screen", app_name=app_name) or [{}])[0]
		url = (screen.get("route") or "").strip()
		if url and not is_desk_route(url):
			found[app_name] = url
	return found


def _app_meta() -> dict[str, dict]:
	"""What each installed app is called and its logo, the way the desk's boot works it out."""
	meta = {}
	for app_name in frappe.get_installed_apps():
		screen = (frappe.get_hooks("add_to_apps_screen", app_name=app_name) or [{}])[0]
		title = screen.get("title") or next(iter(frappe.get_hooks("app_title", app_name=app_name)), None)
		logo = screen.get("logo") or next(iter(frappe.get_hooks("app_logo_url", app_name=app_name)), None)
		meta[app_name] = {"title": title or app_name, "logo": logo}
	return meta
