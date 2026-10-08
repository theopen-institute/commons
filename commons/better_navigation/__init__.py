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

The desk
--------
The desk's own navigation -- the rail of apps, Manage Desk Apps, the Apps screen
arranged from it, and Help and the site's tools in the desk's user menu -- is the
Open Desk app's. This app adds to it where that app offers a place: Desk To Do
puts a tile at the foot of Open Desk's rail (`opendesk.rail.tools`). What is left
here on the desk side:

- `user_menu.py`: the frontend's user menu. The user badge opens a menu of your
  account, display, session defaults, site tools, help and logout
  (`AppSidebar.vue`); `user_menu.py` gives it the Session Defaults fields and
  Navbar Settings rows.
- `website_link.py`: where the frontend's "Website" entry goes.
- `home_page.py`: where you land after logging in, when your roles name more
  than one home page. The other half of the cascade `website_link.py` splits.

Commons Settings' Better Navigation tab has a switch for each part, all off until
ticked (`commons.commons_core.settings`): the frontend's user menu, the home page
priority and Desk To Do (`public/js/desk_todos/`, a To Do panel beside the desk's
notification bell). The Website entry's switch is its own target field, which
does nothing until it is filled in.
"""
