"""Extensions to Frappe itself, and this app's own settings.

Two things, and the first is most of it. Each module here takes a behaviour
Frappe already has -- what an active Workflow says, which roles a doctype's
permission rows grant something to, which of the optional apps this site
actually runs -- and either corrects it or reads it in one place, so the
sections above do not each read it their own way. Nothing in that half is about
leave, procurement, an employee or a request.

The test for belonging is whether the module would still make sense in an app
that had none of this one's *sections*. `workflow` would: it is what
`frappe.model.workflow` says, shaped for an API, and it names no state, role or
action. `doc_perms` would: it reads the
tables behind the Role Permission Manager. `apps` would: it answers which apps
and doctypes a site has, which is how every optional section decides whether it
is here at all.

Navigation passes that test too and is not here. Where the Website button goes,
which role's home page wins and what the desk sidebar's menus hold are all
corrections to Frappe, but they are one design with this app's own sidebar, and
`commons.better_navigation` keeps the design in one place. The test decides
between here and the app root; a section that claims a module outranks it.

`jinja.py` adds `make_qr_code` to Frappe's own Jinja environment, reachable
from every print format, letter head and portal page on the site. `frappe_fixes`
stands in for Frappe endpoints that are broken upstream, each until Frappe fixes
its own. `notifications` and `todos` read Frappe's Notification Log and ToDo for
the session user alone, where core's own endpoints would hand an administrator
the whole site's.

The second thing is what is not an extension to Frappe at all but a fact about
*the app*, and there is nowhere better for a fact about the app than the module
named after it. `Commons Settings` and `settings.py` are what this app calls
itself on the site that runs it, the switches for each place it changes Frappe's
behaviour, and the settings its sections read. `install.py` holds the app's name
and the `before_migrate` hook that refreshes the module map, and `uninstall.py`
is what the app takes with it, leaves and says when it is removed.

What is deliberately *not* here is what is left at the app root: `api.py`, the
session's own identity, which is the one thing every section starts from and
nothing in here needs.

Why the name stutters
---------------------
`commons.commons_core` reads badly and is still right. A Frappe module's
directory is `scrub()` of its name, so the package name is the module name a
System Manager sees in the desk -- and there `Core` is Frappe's own module. This
one had to say whose core it is. The stutter is paid once, in an import line;
the alternative was paid every time somebody browsing a live site had to work
out which `Core` they were looking at.

It is a module in `modules.txt` because it owns a doctype, `Commons Settings`.

The browser halves live under `commons/public/js/`, because esbuild globs only
that tree for `*.bundle.js` entries and a `page_js` hook can only name a file in
it -- `permission_manager_gate.js` for `safer_permissions` is one of each. An
entry may import from anywhere, though, and `commons.better_navigation` keeps its
browser halves beside its server halves for that reason. Each server half says
which file is its other end.
"""
