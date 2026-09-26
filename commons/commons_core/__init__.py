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

`jinja.py` is the newest of them and the plainest. `make_qr_code` is a template
helper reachable from every print format, letter head and portal page on the
site, it belongs to no section, and it would make perfect sense in an app that
had none of this one's -- and the Jinja environment it is added to is Frappe's
own. It was at the app root, which is where it went when the only thing that
could be said about it was which section it *wasn't*.

The second thing is the two exceptions to the test above. Neither is an
extension to Frappe; both are facts about *the app*, and there is nowhere better
for a fact about the app than the module named after it.

`Commons Settings` and `settings.py` are the first -- what this app calls itself
on the site that runs it. It used to live with the navigation, which was one of
its readers; the browser tab and the desk's Awesome Bar are two others.

`install.py` is the second: the `before_migrate` hook that registers this app's
modules with the site, so that a module added to `modules.txt` after the app was
installed somewhere has a `Module Def` before the doctype sync looks for one.
Its own docstring argues the move.

Two exceptions is the ceiling. The test above is the only thing standing between
this module and the place things go when nowhere else is obvious, and it stops
being a test the third time it is waived -- so the next thing that is neither an
extension to Frappe nor a fact about the app belongs with a section, or belongs
in a module of its own.

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

It is a module in `modules.txt` because it owns a doctype, which is the whole of
what earns that line. It did not always: before `Commons Settings` moved here it
was a plain package, and registering it would have created a `Module Def` that
nothing named.

The browser halves live under `commons/public/js/`, because esbuild globs only
that tree for `*.bundle.js` entries and a `page_js` hook can only name a file in
it -- `permission_manager_gate.js` for `safer_permissions` is one of each. An
entry may import from anywhere, though, and `commons.better_navigation` keeps its
browser halves beside its server halves for that reason. Each server half says
which file is its other end.
"""
