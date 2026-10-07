"""Navigation, in the desk and in this app's own frontend, kept as one design.

The two sidebars sit in the same place on the screen and a user crosses between
them all day, so they are built to each other: what one's menus hold, and in
what order, the other's hold too. This module is where both halves live, so a
change to one is made next to the other.

The frontend's frame
--------------------
The frame every page of `/commons` is drawn in: what it is called, and what is in the sidebar.

Everything under `/commons` renders inside one sidebar. What belongs in it is a
decision about the site -- the same idea `Self Service Record` stands for -- so
it is held as documents a System Manager can see and change rather than as
constants in a bundle.

`Commons Workspace` is a named section of the navigation: a title, a mark, and
the rows under it. A row is one of the pages this app ships (see `pages.py`), a
`Self Service Record`, or a Link to an address the site chooses. No page and no
record may sit in two workspaces, and that is enforced on save: the sidebar has to be able to say
which workspace the page you are looking at belongs to, and a page in two of
them has no answer.

The name over all of it is not here. `Commons Settings` used to be, on the
grounds that the sidebar reads it -- but so do the browser tab and the desk's
Awesome Bar, and what it holds is a fact about the app rather than about the
navigation. It is `commons.commons_core.settings` now, and `api.py` puts the two
answers together for the one caller that needs both at once.

A site that has configured none of this is not a broken site. `workspaces.py`
falls back to a default workspace built from whatever self-service and pages
the site has, so an install that never opens the doctype still has a sidebar.

`search.py` is the same navigation read through a search box rather than a
sidebar -- this app's pages offered in the desk's Awesome Bar, and the desk's
doctypes offered in this app's. It is here because every row it can offer comes
from `workspaces.py` and `pages.py`; its own docstring says the rest.

The frontend half is `frontend/src/data/shell.ts`. The split is the same one
`registry.field_definitions` makes for a form: this side says which rows, in
what order, under which heading, and what they are called; that side knows what
a row opens, whether this user may open it, and what the badge on it says.

The rail
--------
`Navigation App` is the level above the modules: an entry on the rail, holding
the modules it offers. A site's apps need not be installed apps -- "Finance"
may hold modules from two of them. Nothing configured, the rail is the
installed apps; configured, it is those apps first and every module they leave
unclaimed still under its installed app. `navigation_apps.py` resolves it and
says why each rule is there.

Frappe 16.50 replaced the desk's navigation: one `Sidebar` per module, a Dock
of the open app's modules, an Apps screen. The rail is built on top of that --
`js/navigation_rail.js` has the Dock list apps where it lists modules, and the
sidebar's header menu list the open app's modules -- and `navigation_apps.py`
reads the modules from Frappe's own boot. A module itself is overridden the way
Frappe offers (a Custom Sidebar layer, or a custom Module Def for a synthetic
one); this module only adds the level above.

The desk's sidebar
------------------
Frappe 16.50's sidebar has its own user menu, keeps the sidebar you came from
in the URL, and has no Website entry, so the desk halves that used to patch
those are gone. What is left:

- `js/user_menu.js` and `user_menu.py`: in the desk, Help moves from the
  sidebar's header menu into Frappe's user menu. In the frontend, the user
  badge opens a menu of your account, display, session defaults, site tools,
  help and logout (`AppSidebar.vue`); `user_menu.py` gives it the Session
  Defaults fields and Navbar Settings rows.
- `website_link.py`: where the frontend's "Website" entry goes.
- `home_page.py`: where you land after logging in, when your roles name more
  than one home page. The other half of the cascade `website_link.py` splits.

Commons Settings' Better Navigation tab has a switch for each desk part, all
off until ticked (`commons.commons_core.settings`): the navigation rail, the
user menu, the home page priority, Desk To Do (`public/js/desk_todos/`, a To Do
panel beside the desk's notification bell) and the Apps screen arranged from
the Navigation Apps (`apps_screen.py`). The Website entry's switch is its own
target field, which does nothing until it is filled in.
"""
