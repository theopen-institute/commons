"""The frame every page of this app is drawn in: what it is called, and what is in the sidebar.

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

The frontend half is `frontend/src/data/shell.ts`. The split is the same one
`registry.field_definitions` makes for a form: this side says which rows, in
what order, under which heading, and what they are called; that side knows what
a row opens, whether this user may open it, and what the badge on it says.
"""
