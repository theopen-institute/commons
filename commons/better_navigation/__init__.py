"""Navigation, in the desk and in this app's own frontend, kept as one design.

The two sidebars sit in the same place on the screen and a user crosses between
them all day, so they are built to each other: what one's menus hold, and in
what order, the other's hold too. This module is where both halves live, so a
change to one is made next to the other.

The frontend's frame
--------------------
The frame every page of `/commons` is drawn in: what it is called, and what is in the sidebar.

Everything under `/commons` renders inside one sidebar, and until now that
sidebar was written down in the frontend twice over -- a registry holding a
single app in `data/apps.ts`, and a hand-written list of rows in
`AppSidebar.vue`. So the name over the navigation, the name of the one
workspace, and which sections a person was offered were all a deploy away from
changing, on a site that had every right to want them different.

This module is the same idea `Self Service Record` already stands for, applied
to the shell: what belongs in the navigation is a decision about the site, so it
is held as documents a System Manager can see and change rather than as
constants in a bundle.

`Commons Workspace` is a named section of the navigation: a title, a mark, and
the rows under it. A row is either one of the pages this app ships (see
`pages.py`) or a `Self Service Record`. No page and no record may sit in two
workspaces, and that is enforced on save: the sidebar has to be able to say
which workspace the page you are looking at belongs to, and a page in two of
them has no answer.

The name over all of it is not here. `Commons Settings` used to be, on the
grounds that the sidebar reads it -- but so do the browser tab and the desk's
Awesome Bar, and what it holds is a fact about the app rather than about the
navigation. It is `commons.commons_core.settings` now, and `api.py` puts the two
answers together for the one caller that needs both at once.

A site that has configured none of this is not a broken site. `workspaces.py`
falls back to the one workspace this app used to hard-code, built from whatever
self-service the site has, so an install that never opens the doctype keeps the
sidebar it already had.

`search.py` is the same navigation read through a search box rather than a
sidebar -- this app's pages offered in the desk's Awesome Bar, and the desk's
doctypes offered in this app's. It is here because every row it can offer comes
from `workspaces.py` and `pages.py`; its own docstring says the rest.

The frontend half is `frontend/src/data/shell.ts`. The split is the same one
`registry.field_definitions` makes for a form: this side says which rows, in
what order, under which heading, and what they are called; that side knows what
a row opens, whether this user may open it, and what the badge on it says.

The desk's sidebar
------------------
The desk halves patch Frappe's own sidebar from `commons.bundle.js`, which
imports them from `js/` here. An entry file has to be under `public/` for
esbuild to find it; what it imports does not.

- `js/user_menu.js` and `user_menu.py`: the user badge at the foot of the
  sidebar opens a menu of your account, display, session defaults, site tools,
  help and logout, and the header menu keeps only navigation. The frontend's
  badge is the same menu (`AppSidebar.vue`), and `user_menu.py` gives it the
  Session Defaults fields and Navbar Settings rows the desk gets on boot.
- `js/website_button.js` and `website_link.py`: where the "Website" entry goes,
  in both sidebars.
- `js/workspace_sidebar_memory.js`: which sidebar a refresh keeps you in.
- `home_page.py`: where you land after logging in, when your roles name more
  than one home page. The other half of the cascade `website_link.py` splits.

Each of these but the Website button has a switch in Commons Settings' Better
Navigation section, off until ticked (`commons.commons_core.settings`); the
button's switch is its own target field, which does nothing until it is filled
in. The user menu's switch covers both sidebars.
"""
