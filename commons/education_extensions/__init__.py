"""This app's education module: the teaching customisations, and who owns them.

Almost nothing in this package is a file, and that is the point of it.

`Education Extensions` is a module a site filled in through the desk: twenty
Custom DocTypes -- `Assessment`, `Assessment Marking`, `Course Grade`,
`Financial Aid Application`, `Student Reflection`, `Prize` and their child
tables -- plus three Reports, three Print Formats, a Web Form, twenty-nine
Custom Fields, and the Server and Client Scripts that drive them. None of it
ships as source. They are `custom = 1` records in the database, and the only
thing tying them to an app is the `module` field naming a `Module Def` that an
app claims.

That is why this directory exists at all. A `Module Def` belongs to whichever
app's `modules.txt` lists its name, and `frappe.model.sync.sync_for` resolves
that name by *importing* `<app>.<scrubbed module>` -- with no guard -- so a
module listed without a package underneath it fails migrate outright. An empty
`__init__.py` is the whole of what the module needs in order to be somewhere.

What the app it came from was
-----------------------------
NepalERP. Its code is gone: the Bikram Sambat date fields it added are
`commons/public/js/bikram_sambat/` now, written from scratch, and the rest was
either dead or a handful of helpers. What could not simply be dropped was this
module, because `frappe.installer.remove_app` deletes every doctype under every
`Module Def` its app owns -- custom ones included, as its own confirmation
prompt says -- and that was several thousand rows of assessment and
financial-aid history.

So the module was moved rather than the data: `Module Def.app_name` says
`commons`, this app's `modules.txt` names it, and uninstalling NepalERP found
nothing of its own left to delete.

There was a second module alongside this one, `NepalERP` itself, taken over for
the same reason and on the same day. It held four Custom DocTypes and no rows of
its own, and it is gone: `Prize` and `Prize Submission` were moved here, where
they belonged, `Approval` and `User Link` to `Commons Core`, and the module was
deleted once it was empty. This one stays because it has a subject; that one had
only a former owner.

The name is kept deliberately. It describes what the module holds, a rename
would have to travel through every record that names it, and what is under it is
a site's own configuration rather than anything this app ships -- so what it is
called is not this app's to change.

Only the workspaces are files
-----------------------------
`workspace/` holds the three that make up the desk navigation for all of it --
Admissions, Assesssments (sic, as the site named it), Course Grades. They are
here rather than left as database rows because migrate's own
`remove_orphan_entities` deletes any public `Workspace` that has a module and an
app but no backing file, and theirs was in the app being retired. The `app`
field in each file is null; Frappe fills it in from whichever app syncs it.
"""
