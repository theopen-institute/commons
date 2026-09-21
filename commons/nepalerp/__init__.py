"""The other module the retired NepalERP app owned, kept for the records under it.

The same arrangement as `commons.education_extensions`, and its docstring is the
argument for both: this is a `Module Def` a site filled in through the desk, and
the package exists because a module named in `modules.txt` must be importable or
`frappe.model.sync.sync_for` fails.

What is under it is smaller and less alike: `Prize` and `Prize Submission`,
`Approval`, `User Link`. All `custom = 1`, none of them this app's, and nothing
here ships a file for any of them.

Two child tables under it *were* the old app's own source -- `Item Spare Part
Parent Details` and `Salary Structure Assignment Component` -- and are not
carried over. The first had a `Custom Field` on `Item` pointing at it and no
rows at all; the second had thirteen rows under
`Salary Structure Assignment.component_adjustments`, a field no `Custom Field`
on this site defines, so nothing could read them. Both are for deleting with the
app rather than absorbing into this one, and the `Item` custom field has to go
first or its column will point at a doctype that no longer exists.

The name is the retired app's, and is kept for the reason the module beside it
keeps its own: a rename travels through every record that names the module, and
what a site calls its own module is not this app's to decide. It is worth
revisiting once the four doctypes under it are looked at properly -- unlike
`Education Extensions`, this module has no subject, only a former owner.
"""
