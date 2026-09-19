"""The pages this app ships, as a workspace is allowed to name them.

A workspace row is one of two things: a `Self Service Record`, which is
configuration and says its own name, or one of the pages below, which is code.
This module is the list of the second kind.

The values are the keys the API sends and `frontend/src/data/shell.ts` resolves
-- into a route, into whether this user may open it at all, and, for the three
request sections, into the badge an approver reads. The two halves have to agree
on this set, the way `hooks.py` and the old frontend app registry had to agree
on theirs.

The dictionary keys are what a System Manager picks in the desk, and they are
worded as the sidebar words the row rather than as the code spells it -- the
person choosing is choosing a row they have seen. They are stored values, so
`commons_workspace_item.json` lists exactly these four as the Select's options
and `CommonsWorkspaceItem.validate` refuses anything else; a rename here is a
rename there and a patch for anything already saved.

Deliberately not here: the label and the icon each page is drawn with. Those
live in the frontend, because a Tailwind build can only compile an icon class it
can see written down in the source it scans -- see `self_service/icons.py`,
which is the same problem solved the same way for the icons that *are*
configuration. A workspace row may still override either, and an override is
held to the icon palette for exactly that reason.
"""

PAGES: dict[str, str] = {
	"Announcements": "announcements",
	"Leave Request": "leave",
	"Expense Claim": "expense",
	"Procurement": "procurement",
}

# What the default workspace holds when a site has configured no workspace of
# its own, in sidebar order: the ungated page first as a bare row, then
# everything self-service under one heading, then the three things a person
# raises under another. This is the sidebar this app hard-coded before
# workspaces were documents, and reproducing it exactly is the point.
DEFAULT_REQUEST_PAGES: tuple[str, ...] = ("leave", "expense", "procurement")
