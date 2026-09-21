"""Extensions to Frappe itself, and this app's own settings.

Two things, and the first is most of it. Each module here takes a behaviour
Frappe already has -- where the Website button goes, which role's home page
wins, what an active Workflow says, which roles a doctype's permission rows
grant something to, which of the optional apps this site actually runs -- and
either corrects it or reads it in one place, so the sections above do not each
read it their own way. Nothing in that half is about leave, procurement, an
employee or a request.

The test for belonging is whether the module would still make sense in an app
that had none of this one's *sections*. `website_link` and `home_page` would:
they are two halves of a cascade in `frappe.website.utils` that Frappe never
separated. `workflow` would: it is what `frappe.model.workflow` says, shaped for
an API, and it names no state, role or action. `doc_perms` would: it reads the
tables behind the Role Permission Manager. `apps` would: it answers which apps
and doctypes a site has, which is how every optional section decides whether it
is here at all.

The second thing is `Commons Settings` and `settings.py` -- what this app calls
itself on the site that runs it. That is not an extension to Frappe, and it is
the one exception to the test above: it is a fact about *the app*, and there is
nowhere better for a fact about the app than the module named after it. It used
to live with the navigation, which was one of its readers; the browser tab and
the desk's Awesome Bar are two others.

What is deliberately *not* here is what is left at the app root -- `api.py`, the
session's own identity, which is the one thing every section starts from and
nothing in here needs -- and `install.py`, which registers this app's modules
with the site.

Why the name stutters
---------------------
`commons.commons_core` reads badly and is still right. A Frappe module's
directory is `scrub()` of its name, so the package name is the module name a
System Manager sees in the desk -- and there `Core` is Frappe's own module. This
one had to say whose core it is. The stutter is paid once, in an import line;
the alternative was paid every time somebody browsing a live site had to work
out which `Core` they were looking at.

It is a module in `modules.txt` because it owns a doctype, which is the whole of
what earns that line. It did not always: before `Commons Settings` moved here it
was a plain package, and registering it would have created a `Module Def` that
nothing named.

The browser halves stay under `commons/public/js/`, because that is the only
tree esbuild globs for bundles and the only tree a `page_js` hook can name --
`website_button.js` here, `permission_manager_gate.js` for `safer_permissions`.
Each one's server half says which file is its other end.
"""
