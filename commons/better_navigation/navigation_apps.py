"""The rail: which apps it lists, and which sidebars each one offers.

Three levels, in this app's terms rather than Frappe's:

    Navigation App   an entry on the rail
      Sidebar        a module, picked from the app's top menu (a `Workspace Sidebar`)
        Item         a row in the sidebar (a `Workspace Sidebar Item`)

Only the top level is new. The bottom two are v16's own Workspace Sidebar and its
items, which already render, filter by permission and have an editor; this adds
the grouping above them that Frappe has no document for. (Upstream's v17 draws
the same three levels as Dock, Sidebar and Sidebar Item, so a `Navigation App`
maps onto a Dock when that arrives.)

"App" here is not an installed app. A `Navigation App` is whatever grouping a
site wants on its rail -- "Finance" holding sidebars from ERPNext and from this
app, say -- and a site may add as many as it likes.

One can also stand for an installed app, or for "Other", by naming it in
`installed_app`. It then takes that app's place on the rail rather than
appearing beside it: in its own Rail Order, under its own title, roles and
mark, falling back to the app's hooks for the logo and the frontend. Its
sidebars table either adds to what the app already holds (and relabels
anything it lists) or, set to Replace, is the whole list, and what the app
would have held goes to Other. The table's row order is the order the rail
lists them in; only what nobody has put in order is sorted, landing module
first (see `_default_order`). The table can also hold Category rows, a heading
over the modules after it, and Spacer rows, a gap; see `_layout`. Hidden takes it off the rail, and its sidebars
with it. "Other" is bindable like any installed app: the one group no hooks
describe, but as much the site's to rename, restrict or hide.

The fallback is the installed apps
----------------------------------
A site that has configured nothing still gets a rail: one entry per installed
app, holding the sidebars that belong to it. And a site that has configured some
apps loses nothing it did not mention -- every sidebar no `Navigation App`
claims is still grouped under its installed app, after the configured ones. So
installing an app puts it on the rail without anybody touching this, and
configuring is only ever a matter of claiming what should move.

Which installed app a sidebar belongs to is not one field. A standard sidebar
names its app; one made on the site usually does not (the form only offers the
field for standard ones). So it is asked in turn: the sidebar's own `app`, then
the app of its `module` -- the sidebar's own fields and nothing else, the same
order core's header follows when it names the app. A sidebar neither places is
grouped under "Other", which is the honest answer and a hint that it wants a
module or claiming.

Two rules
---------
*A sidebar is in one app.* The header has to say which app and module the page
you are on belongs to, and a sidebar in two apps has no answer. Enforced when a
`Navigation App` is saved; here the first to claim one keeps it, so a conflict
that got past the form still resolves the same way every time.

*A role-restricted app still claims its sidebars.* Otherwise somebody without
the role would find the same sidebars back under their installed app, and the
restriction would only have moved them. Roles decide who sees the app on the
rail; they are not permission, and a sidebar a person cannot open is filtered
by the browser against what the boot already allows them, the same split
`workspaces.py` makes for the frontend's rows.

Personal sidebars (`for_user`) are left out of the fallback for everyone but
their owner, and cannot be claimed at all: a rail shared by a site is no place
for one person's sidebar.
"""

import frappe
from frappe import _

APP = "Navigation App"
APP_SIDEBAR = "Navigation App Sidebar"
SIDEBAR = "Workspace Sidebar"

# Where a sidebar goes when nothing says which app it belongs to.
OTHER = "Other"
OTHER_LOGO = "/assets/commons/images/commons-other-logo.svg"

# A Navigation App bound to an installed app either adds its sidebars table to
# what the app already holds, or replaces it.
ADD = "Add"
REPLACE = "Replace"

# What a row of a Navigation App's sidebars table is. Rows saved before the
# column existed are modules.
MODULE = "Sidebar"
CATEGORY = "Category"
SPACER = "Spacer"

# The module an app starts from, when its name does not say so already.
HOME = "home"


# The site-level half of the rail: everything `resolve` reads except the user.
CACHE_KEY = "commons_navigation_rail"


@frappe.whitelist()
def get_navigation_apps() -> list[dict]:
	"""The rail, for the session user -- nothing while the rail is off, or for a website user."""
	from commons.commons_core import settings

	user_type = frappe.get_cached_value("User", frappe.session.user, "user_type")
	if user_type != "System User" or not settings.feature_enabled(settings.ENABLE_NAVIGATION_RAIL):
		return []
	return navigation_apps()


def extend_bootinfo(bootinfo: "frappe._dict") -> None:
	"""Hand the desk its rail, when the rail is switched on.

	On the boot rather than behind a call, so the rail draws with the sidebar
	instead of after it. Left off entirely while the switch is off: the rail's
	script checks the same flag and installs nothing.
	"""
	from commons.commons_core import settings

	if settings.feature_enabled(settings.ENABLE_NAVIGATION_RAIL):
		bootinfo.navigation_apps = navigation_apps()


def navigation_apps(user: str | None = None) -> list[dict]:
	"""The rail for `user` (the session user by default), read from the site."""
	user = user or frappe.session.user
	return resolve(**_site_inputs(), user=user, user_roles=set(frappe.get_roles(user)))


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
			"sidebars": _sidebars(),
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
) -> list[dict]:
	"""The rail, from plain data: configured apps first, then the installed ones.

	`configured` is the enabled Navigation Apps in rail order, each with its
	`sidebars` rows (`type`, `sidebar`, `label`), `roles`, and optionally the
	`installed_app` it stands for, its `sidebar_mode` and whether it is `hidden`.
	`sidebars` is every Workspace Sidebar (`name`, `header_icon`, `app`,
	`module`, `for_user`). The rest say what an installed app is called and
	which app a module belongs to, and `frontends` where an installed app's own
	frontend is, outside the desk.

	Every entry carries `frontend` -- `{label, url}` or None -- beside its
	`sidebars`, which are modules only: a module may carry a `category` or
	`space_before` to draw above it (see `_layout`). An app is on the rail if it has either: a frontend with no desk
	sidebars (Frappe Builder, say) is somewhere to go too.
	"""
	frontends = frontends or {}
	by_name = {sidebar["name"]: sidebar for sidebar in sidebars}
	claimed: set[str] = set()

	# Claims first, all of them, so what is left for the installed apps is known
	# before any entry is drawn: a bound app early on the rail still gets the
	# sidebars no later app claims.
	claims: list[list[dict]] = []
	for app in configured:
		entries = []
		for row in app["sidebars"]:
			if row_type(row) != MODULE:
				entries.append(_marker(row))
				continue
			sidebar = by_name.get(row["sidebar"])
			# Deleted since, personal, or already claimed by an earlier app.
			if not sidebar or sidebar.get("for_user") or sidebar["name"] in claimed:
				continue
			claimed.add(sidebar["name"])
			entries.append(_entry(sidebar, row.get("label")))
		claims.append(entries)

	grouped: dict[str, list[dict]] = {}
	for sidebar in sidebars:
		if sidebar["name"] in claimed:
			continue
		if sidebar.get("for_user") and sidebar["for_user"] != user:
			continue
		owner = installed_app_of(sidebar, module_apps)
		if owner not in installed_apps:
			owner = OTHER
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
		if app.get("hidden"):
			continue
		roles = set(app.get("roles") or ())
		if roles and not roles & user_roles:
			continue

		own_mark = app.get("logo") or app.get("icon")
		frontend = _frontend(
			app["title"],
			app.get("frontend_url") or (frontends.get(target) if target else None),
			app.get("frontend_label"),
		)
		if entries or frontend:
			rail.append(
				{
					# A bound app keeps its installed app's key: the browser finds an
					# app by it and remembers each app's last module under it.
					"key": f"app:{target}" if target else f"navigation-app:{app['name']}",
					"title": app["title"],
					"icon": app.get("icon") or None,
					"logo": app.get("logo") or (None if own_mark else _default_logo(target, meta)),
					"configured": True,
					"sidebars": entries,
					"frontend": frontend,
				}
			)

	for app_name in [*installed_apps, OTHER]:
		if app_name in bound:
			continue
		entries = grouped.get(app_name) or []
		meta = app_meta.get(app_name) or {}
		title = meta.get("title") or (OTHER if app_name == OTHER else app_name)
		frontend = _frontend(title, frontends.get(app_name))
		if not entries and not frontend:
			continue
		rail.append(
			{
				"key": f"app:{app_name}",
				"title": title,
				"icon": None,
				"logo": _default_logo(app_name, meta),
				"configured": False,
				"sidebars": _default_order(entries, {title, app_name}),
				"frontend": frontend,
			}
		)
	return rail


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
	"""Which installed app a sidebar belongs to, asked in the order the module docstring gives."""
	if sidebar.get("app"):
		return sidebar["app"]
	module = (sidebar.get("module") or "").strip()
	return module_apps.get(module)


def _default_order(entries: list[dict], app_names: set[str]) -> list[dict]:
	"""Modules nobody has put in order: the app's landing module, then the rest.

	Workspace Sidebar has no order of its own, and the only one core has, the
	Desktop Icons' `idx`, is a rail's worth of ties. So alphabetical, by what
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


def _entry(sidebar: dict, label: str | None = None) -> dict:
	return {
		"sidebar": sidebar["name"],
		"label": (label or "").strip() or sidebar["name"],
		"icon": sidebar.get("header_icon") or None,
	}


def installed() -> bool:
	"""Whether `Navigation App` is on this site yet.

	The same deploy window `workspaces.installed` guards: code lands before
	migrate creates the doctype. Until then the rail is the installed apps alone.
	"""
	return bool(frappe.db.exists("DocType", APP, cache=True))


def _configured() -> list[dict]:
	if not installed():
		return []

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
		],
		order_by="rail_order asc, title asc",
	)
	if not apps:
		return []

	names = [app.name for app in apps]
	# `type` arrives with a migrate; until then every row is a module.
	fields = ["parent", "sidebar", "label"]
	if frappe.db.has_column(APP_SIDEBAR, "type"):
		fields.append("type")
	rows = frappe.get_all(
		APP_SIDEBAR,
		filters={"parent": ["in", names], "parenttype": APP},
		fields=fields,
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


def _sidebars() -> list[dict]:
	return frappe.get_all(SIDEBAR, fields=["name", "header_icon", "app", "module", "for_user"])


def _frontends() -> dict[str, str]:
	"""Each installed app's own frontend, outside the desk, as its hooks declare it.

	`navigation_frontend_url` first, for an app whose frontend is not on the
	apps screen (this one: an `add_to_apps_screen` entry would also put a
	second Commons tile on the Desktop), then the apps screen's `route`, the
	hook the title and logo already come from. Code, not site data, so the rail
	describes an installed app the same way on every site; a site that wants a
	different link sets it on a Navigation App. Routes that only open a desk
	page are not frontends.
	"""
	found: dict[str, str] = {}
	for app_name in frappe.get_installed_apps():
		screen = (frappe.get_hooks("add_to_apps_screen", app_name=app_name) or [{}])[0]
		url = next(iter(frappe.get_hooks("navigation_frontend_url", app_name=app_name)), None)
		url = (url or screen.get("route") or "").strip()
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
