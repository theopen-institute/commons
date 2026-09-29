"""The attendance register's side of Education: `attendance`, and nothing else.

A plain package, not a Frappe module. The name is a leftover of what it was.

`Education Extensions` was a module this app claimed and did not fill: the
Open Institute's register keeps twenty Custom DocTypes under it (`Assessment`,
`Course Grade`, `Financial Aid Application`, `Prize` and their child tables),
with the reports, print formats, web form, fields and scripts around them. It
came from NepalERP, and this app took it over so that uninstalling NepalERP --
`frappe.installer.remove_app` deletes every doctype under every `Module Def` its
app owns, custom ones included -- would not delete several thousand rows of
assessment and financial-aid history.

Owning it had the same danger the other way round, and it shipped the module's
three workspaces to every site, including ones without Education. So the module
is now the register's own: a custom `Module Def`, which no app's uninstall
touches, with the workspaces kept there as site records. That move was made on
each site by `commons.commons_core.education_handover`, which also removed the
workspaces from sites that had never used them.
"""
