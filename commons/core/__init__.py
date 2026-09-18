"""Extensions to Frappe itself: things core already does, done differently.

Nothing in here is about leave, procurement, an employee or a request. Each
module takes a behaviour Frappe already has -- where the Website button goes,
which role's home page wins, what an active Workflow says, which roles a
doctype's permission rows grant something to -- and either corrects it or reads
it in one place so the sections above do not each read it their own way.

The test for belonging here is whether the module would still make sense in an
app that had none of this one's doctypes. `website_link` and `home_page` would:
they are two halves of a cascade in `frappe.website.utils` that core never
separated. `workflow` would: it is what `frappe.model.workflow` says, shaped for
an API, and it names no state, role or action. `doc_perms` would: it reads the
tables behind the Role Permission Manager.

What is deliberately *not* here is what is left at the app root -- `api.py`, the
session's own identity, which is the one thing every section starts from and
nothing in here needs -- and `install.py`, which registers this app's modules
with the site and so is about the app rather than about Frappe.

Not a module in `modules.txt`, yet
----------------------------------
A Frappe module earns that line by owning desk artifacts: doctypes, pages,
reports, a workspace. This owns none -- it is Python that runs against core's own
doctypes -- so registering it would create a `Module Def` that nothing names and
buy nothing but a row.

The directory is the point regardless: it is where the next base extension goes,
and it makes the boundary between "extends Frappe" and "is this app's own" something
you can see in the tree. If something in here does grow a doctype, the migration
is one line in `modules.txt`, a `doctype/` folder, and nothing else --
`commons.install.sync_module_defs` already creates `Module Def` records for
modules added to an app after it was installed.

The browser halves stay under `commons/public/js/`, because that is the only
tree esbuild globs for bundles and the only tree a `page_js` hook can name --
`website_button.js` here, `permission_manager_gate.js` for `safer_permissions`.
Each one's server half says which file is its other end.
"""
