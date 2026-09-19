# Search

The desk has one search box that does everything — Ctrl+K, type three letters,
press Enter. Staff who work in `/commons` had nothing. This is that box, in both
directions: the desk's bar now finds this app's pages, and this app has the bar.

## In the desk

Nothing to set up. Open the Awesome Bar and type the name of a page — *leave*,
*announcements*, whatever your workspace rows are called — and the page appears
beside the desk's own results, marked with the app's name. Picking it leaves the
desk for `/commons`.

What it offers is what your sidebar offers: rows from **Commons Workspace**
documents, under the names those documents give them, and only the ones you have
permission to open. Rename a row and it is found under the new name.

It offers pages, not documents. An individual leave application is already found
by the desk's own search, and it opens where it can actually be read — the desk
form, not a self-service page that only ever shows you your own record.

## In the app

Two dialogs, the same two the desk has.

**Ctrl+K** (⌘K on a Mac) opens the search bar. It searches this app and the
desk together, which is the point of it — you should not have to know which
application a thing lives in before you can look for it. What it offers:

- **Pages** — every row of every workspace you can open.
- **New …** — *New leave request*, *New expense claim*, *New procurement
  request*, for the ones you may raise. Picking one opens the page and its form
  together. Typing `new` first narrows to these.
- **The desk's doctypes** — *Employee List*, *Account Tree*, *New Supplier*,
  *HR Settings*. Everything you could reach from the desk's own bar, named the
  way the desk names it. These open in the desk.
- **Documents** — the record itself. Type a person's name and their employee
  record, their leave applications and anything else mentioning them appear,
  with the document type on the right and the fields that matched shown
  beneath. These open in the desk too.
- **Recents** — where you have been in this app, most recent first. This is
  also what an empty box shows, ordered by how often you go there.
- **Search for …** — hands what you have typed to Global Search, for the full
  results table.

Everything is ranked together on one scale. A page of this app wins a tie
against a desk row of the same name, and anything whose *name* matches what you
typed comes above a document that merely mentions it.

Arrow keys move, Enter picks, Ctrl+K closes it again. Holding Ctrl or ⌘ while
picking opens it in a new tab. The documents arrive a moment after the rest —
they are a database query, and the rest is already in the browser.

The panel is built to the desk's own measurements — the same width, the same
place on the screen, the same rows and the same key hints along the bottom — so
that crossing between the two does not feel like crossing between two
programs.

Two habits from the desk carry over. A trailing word filters by kind, so
`leave new` shows only the *New* row. And recents are per browser, not per
account — a different machine starts with an empty list.

**Ctrl+G** opens Global Search, which asks the server for *documents* rather
than pages. Results arrive grouped by document type, with the fields that
matched shown beside each one and the search terms marked. `&` joins terms:
`marie&john` finds what mentions both.

Ctrl+K and Ctrl+G swap between the two dialogs, carrying whatever you have
typed.

### Filtering Global Search

Above the results is a row of document-type filters: **All**, then the types you
have pinned, then **More**, which lists the rest and lets you pin and unpin.
Pins are per browser.

The list of types comes from **Global Search Settings**, and reading that record
is a System Manager's right — so most people see **All** alone, and search
everything they are allowed to see. That is the desk's behaviour too.

### Who sees it

Everything that opens in the desk — doctypes, documents, and Global Search
itself — is absent for anyone whose roles do not open the desk. There is no page
in this app that shows an arbitrary document, so for those users every one of
those rows would be a dead end. They keep the Ctrl+K bar, which then offers this
app's own pages, forms and recents, and works the same for everyone else.

Nothing in either dialog widens what anyone can see. Pages are filtered by the
same permissions the sidebar uses, and documents by the same checks the desk's
Global Search makes — the site's Global Search Settings, your read permissions,
and a check on each document before it is returned.

## What is not here

Reports, workspaces, dashboards and desktop icons. The desk's bar offers all
four; this one stops at doctypes and documents, which are the ways to reach a
*record*. The desk is one click away for the rest.

And two things that work by evaluating what you typed as code: the calculator
(`=12*4`) and the random password generator. That is not a trade worth making
for a box that takes its text from the address bar.
