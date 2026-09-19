# Naming the app, and its workspaces

Everything staff open under `/commons` is drawn inside one sidebar: a mark, the
workspace you are in, the name of the app under it, and the rows of that
workspace. All of it is configuration. An organisation that does not call this
"Commons", or that wants its staff pages split into more than one place, changes
documents rather than code.

## The name

**Commons Settings** is a single record with one field, **Title**. It is the
line under the workspace in the sidebar header, and the browser tab's title.
Left blank it reads *Commons*.

It is the app's name, not a workspace's: it stays put as you move between
workspaces, which is what makes the bold line above it mean something.

## The workspaces

A **Commons Workspace** is a named section of the navigation — a title, a mark,
and the rows under it, in order.

| Field | What it does |
| --- | --- |
| **Title** | The bold line in the sidebar header, and the workspace's entry in the switcher. |
| **Enabled** | A disabled workspace is offered to nobody. |
| **Icon** | The mark beside it in the switcher — a lucide name such as `lucide-inbox`. |
| **Logo** | The 32px mark at the top of the sidebar. Left blank it is this app's own. |
| **Order** | Where it sits in the switcher. Ties fall back to the title. |
| **Rows** | The navigation itself. |

Each row is one of two things:

- a **Page** this app ships — Announcements, Leave Request, Expense Claim or
  Procurement;
- a **Self Service Record**, which is a record type already configured under
  that doctype, and which already says what it is called and what it is drawn
  with.

A row may also carry a **Heading** and, for a page, its own **Label** and
**Icon**. Consecutive rows sharing a heading are drawn as one collapsible group;
a row with no heading stands on its own, above the groups. Overriding the label
is how a site renames *Leave Request* to *Time off* without touching the page
behind it.

Icons are held to the palette in `commons/self_service/icons.py` — the build
compiles only the icon classes it can read in the source, so an icon outside
that list would draw as an empty square. Saving tells you which names are
available.

## The one-workspace rule

A page, and a record type, belongs to exactly one workspace. The second
workspace to claim one is refused on save, and told which workspace has it
already.

That is not tidiness. The sidebar header names the workspace the page you are
looking at belongs to, and the switcher takes you to the others; a page in two
workspaces has no answer to "which one am I in".

A disabled workspace claims nothing, so a row can be moved by disabling one
workspace, or by taking the row out of it.

## What people actually see

Nothing here is a permission. A workspace lists what the *site* offers, and each
row is then shown to a user or not according to the permissions that row already
answers to:

- a **request section** appears for someone who may read that kind of request,
  and carries the pending-approvals badge for someone who may decide them;
- a **self-service row** is shown to everyone, and the page behind it explains
  an account with no record of its own — which is far more use than a row that
  quietly is not there;
- **Announcements** is ungated.

A workspace with nothing in it for you is not offered to you at all, and the
switcher only lists the ones you can open. Someone who can open nothing anywhere
lands on the "Nothing to show you" page.

## A site that configures none of this

There is no need to create a workspace. A site with none gets the one this app
has always had — **Staff Member**: announcements, then every self-service record
type under *Profile*, then leave, expenses and procurement under *Requests*.
Create a single workspace and it replaces that default entirely, so the first
one you write should say everything you want in the sidebar.

The same is true of a workspace that has been emptied: a workspace whose every
row names a record type that has since been disabled resolves to nothing, is not
offered, and — if it was the only one — the default comes back.
