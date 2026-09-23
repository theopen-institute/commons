"""Accounts in Google Workspace: the user operations, as plain functions.

Nothing here knows about a doctype, a field or a record. These take an address
or a Google user id and return an account or an id, and whatever on this site
wants to hold on to the result decides that for itself -- a document event, a
button, a Server Script, a patch. That is the whole reason this is a section of
its own rather than twenty lines inside somebody's controller.

Addresses in, ids out
---------------------
An address is what the two systems can agree on to begin with, so "does this
person have an account" starts as a question about an address -- and, unlike
Auth0, Google answers it without ambiguity. There is one directory, an address
is unique across it, and `GET users/{address}` either returns the account or
404s. There is no connection to narrow to and no second account holding the same
address, so `find` is a single call with nothing to disambiguate.

What should be stored afterwards is Google's `id` -- a twenty-ish digit string
-- and not the address. An address can be changed, by an administrator, without
this site being told; an integration that re-derives the account from the
current address quietly starts pointing at nothing, or at whoever was given the
freed-up address next. The id never moves, survives a rename, and is what
`users/{key}` should be called with from then on. Every function that creates or
finds an account here returns the id for that reason.

`find` also matches aliases, because Google does. An address that is somebody's
alias answers with that somebody's account, which is the honest answer to what
is being asked -- the address is taken, and here is what has it.

Nothing is immediate
--------------------
The one thing to hold on to before writing anything that calls two of these in a
row. Google's own documentation is explicit that a created account is not ready
when the create returns: a `GET` a second later can 404, a photo upload can fail
against an account the Admin console already lists, and an alias can take hours
before it receives mail. `create` therefore returns and stops. Photos, aliases
and anything else that follows belong in a background job that can retry --
`frappe.enqueue` with the id this returned -- and not on the next line.

Passwords, and why there are any
--------------------------------
The Auth0 section never knows anybody's password: it creates an account with a
random one, throws it away, and hands out a one-time ticket instead. Google has
no ticket. An account an administrator creates is reachable only by a password
that administrator sets, so this section generates one, returns it, and says
plainly that it is a credential in transit from the moment it does.

`generate_password` makes one. `create` and `set_password` take one or make
their own and return what they used. What happens to it after that -- shown once
on a screen, texted, put in a sealed letter -- is the caller's, and it should
not be written to a field, a log or a comment on the way.

Extending this
--------------
The Directory API is large and this is the part of it this app has needed.
Anything else is a call rather than a change here::

	client.directory("GET", "orgunits", params={"customerId": "my_customer"})
	client.directory("POST", f"users/{key}/signOut")

with the caveat that anything needing a scope beyond `client.SCOPES` needs it
added in two places -- see that constant.
"""

import base64
import secrets
from urllib.parse import quote

import frappe
from frappe import _

from commons.google_workspace import client

# "Entity already exists." What an insert answers when the address is already a
# primary address or an alias somewhere in the domain.
ALREADY_EXISTS = 409

# "Resource Not Found: userKey." Meaningful to `get`, which reports it as an
# absence, and to `delete` and `remove_alias`, which are asked to reach an end
# state rather than to perform an act.
NOT_FOUND = 404

# Google's own floor is eight characters. Twenty because this is generated
# rather than typed from memory, and the only moment anybody has to handle it is
# the one sign-in before `changePasswordAtNextLogin` makes them pick their own.
PASSWORD_LENGTH = 20
MIN_PASSWORD_LENGTH = 8

# Deliberately missing `l`, `I`, `O`, `0` and `1`. This password gets read off a
# screen and typed on a phone keyboard exactly once, and the failure mode of an
# ambiguous character there is somebody deciding the account is broken.
LOWER = "abcdefghijkmnopqrstuvwxyz"
UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"
DIGITS = "23456789"
SYMBOLS = "!@#$%*-_=+"

# What Google will accept as a profile photo, spelled the way it wants them --
# bare format names, not media types. Sending `image/jpeg` here earns a 400 that
# says nothing about which field it is complaining about.
PHOTO_FORMATS = ("JPEG", "PNG", "GIF", "BMP", "TIFF", "WEBP")

# The spellings people actually have to hand: a `File` on this site carries a
# media type, and that is what a caller will pass without thinking about it.
PHOTO_ALIASES = {
	"image/jpeg": "JPEG",
	"image/jpg": "JPEG",
	"image/pjpeg": "JPEG",
	"image/png": "PNG",
	"image/gif": "GIF",
	"image/bmp": "BMP",
	"image/x-ms-bmp": "BMP",
	"image/tiff": "TIFF",
	"image/webp": "WEBP",
	"jpg": "JPEG",
}

# Google's documented ceiling. Checked here so an oversized photo is a sentence
# rather than a 400, and so a 10MB body is not sent to find that out.
MAX_PHOTO_BYTES = 10 * 1024 * 1024

# What `search` asks for when a caller does not say. Google's own ceiling is
# 500.
PAGE_SIZE = 100


def _segment(value: str) -> str:
	"""A user key or an alias, escaped to be one path segment and no more.

	`safe=""` rather than Frappe's own `quoted`, which leaves `/` alone because
	it is meant for whole URLs. A key here is an address or a numeric id, and an
	address contains an `@` -- which is legal unescaped and escaped anyway, on
	the principle that a path segment built from a value somebody typed should
	not be able to reach a different endpoint than the one intended.
	"""
	return quote(value, safe="")


def generate_password(length: int = PASSWORD_LENGTH) -> str:
	"""A random password strong enough for any domain policy, from `secrets`.

	One character from each of the four classes before anything else, because a
	domain with password strength enforcement turned on rejects an all-hex
	string and the rejection arrives as a 400 about `password` that reads like a
	bug in this app.

	`secrets` rather than `frappe.generate_hash`, which returns hex and so
	cannot satisfy that, and rather than `random`, which is seeded predictably
	enough that a sequence of passwords generated in one process is not a secret
	at all.
	"""
	length = max(length, MIN_PASSWORD_LENGTH)
	pools = (LOWER, UPPER, DIGITS, SYMBOLS)
	alphabet = "".join(pools)

	chosen = [secrets.choice(pool) for pool in pools]
	chosen += [secrets.choice(alphabet) for _ in range(length - len(pools))]
	# Otherwise every password has its lower/upper/digit/symbol in that order,
	# which is a quarter of the entropy given away for nothing.
	secrets.SystemRandom().shuffle(chosen)
	return "".join(chosen)


def get(user_key: str) -> dict | None:
	"""One account by its id or any of its addresses, or `None` if there is none.

	`None` rather than a refusal, because the ordinary caller is checking
	whether an id it stored a year ago still points at anything -- an account
	deleted in the Admin console is a state to handle, not an error to raise.
	Every other refusal still raises: a withdrawn delegation must not read as an
	account that is not there.

	Worth knowing that a 404 here is also what a just-created account answers
	for a while. That is the propagation delay the module docstring describes,
	and it is indistinguishable from an absence at this level -- which is why
	nothing in this section polls for an account it has just made.
	"""
	try:
		return client.directory("GET", f"users/{_segment(user_key)}")
	except client.GoogleWorkspaceError as refusal:
		if refusal.status == NOT_FOUND:
			return None
		raise


def find(email: str) -> str | None:
	"""The id of the account reachable at this address, or `None`.

	A direct `GET users/{address}` rather than a search query, and the
	difference matters more here than the extra call it saves. `users.list` with
	a `query` is served from Google's search index, which is eventually
	consistent by design: an account created a minute ago is frequently not in
	it, and an account renamed an hour ago is frequently still in it under the
	old address. Asking for the resource asks the directory itself.

	Aliases count. Google resolves an alias to the account holding it, and so
	does this, because what a caller means by this question is almost always
	"is this address taken, and by whom" rather than "is this address somebody's
	primary". `aliases` is how to tell the two apart afterwards.
	"""
	account = get(email)
	return (account or {}).get("id")


def search(query: str, max_results: int = PAGE_SIZE) -> list[dict]:
	"""Accounts matching a Directory API search expression -- one page of them.

	For the human questions `find` cannot ask: everyone in a department, everyone
	whose surname is this, everyone suspended. The expression is Google's own --
	`"givenName:ann*"`, `"orgUnitPath=/Staff"`, `"isSuspended=true"` -- and the
	reference for it is the Admin SDK's "Search for users" page.

	The search index, with everything that implies. It lags the directory by
	minutes and sometimes longer, so this is the wrong way to check whether an
	account exists and the right way to ask a question no single address
	answers. `find` is the other one.

	One page. Google returns a `nextPageToken` when there are more, and a caller
	that needs to walk them has `client.directory` and no need for this to grow
	a paging protocol it would be the only user of.
	"""
	answer = client.directory(
		"GET",
		"users",
		params={
			"customer": client.credentials().customer_id,
			"query": query,
			"maxResults": max_results,
		},
	)
	return (answer or {}).get("users") or []


def create(
	email: str,
	given_name: str,
	family_name: str,
	password: str | None = None,
	**fields,
) -> str:
	"""A new account for this address, and the id Google gave it.

	The three arguments are required because Google requires them: an account
	has a primary address and a given and family name, and an insert without any
	of the three is a 400. Everything else has a default or is optional.

	`fields` goes to Google as it is, in Google's own spelling, so anything the
	endpoint accepts can be passed without this function growing an argument for
	it. Anything given there wins over the defaults below, including `password`,
	`orgUnitPath` and `changePasswordAtNextLogin`, so a caller with its own
	arrangement is not fighting this one. The ones worth knowing::

		recoveryEmail="ann@example.net"          # personal address, for recovery
		recoveryPhone="+254712345678"            # E.164, the leading + required
		phones=[{"value": "+254712345678", "type": "mobile", "primary": True}]
		organizations=[{"title": "Registrar", "department": "Admissions",
		                "primary": True}]
		externalIds=[{"value": "EMP-0041", "type": "organization"}]
		orgUnitPath="/Staff"
		suspended=True                           # created dormant

	Two of those are list-valued, and a list-valued field is *replaced* whole on
	a later `update` rather than added to. That is harmless here, where there is
	nothing to replace, and is the thing to remember when the same key is passed
	to `update`.

	An address at a domain this Workspace account does not own is a 400 or a
	403 from Google rather than anything this function can catch -- it does not
	know which domains are owned, and asking would be a call and a scope for a
	guess the answer to which is already about to arrive.

	On the password. One is generated if none is given, and unlike the Auth0
	section's equivalent it is *not* thrown away -- it cannot be, because there
	is no ticket flow to reach the account by afterwards. But it is not returned
	either, because this function returns an id. A caller that wants a usable
	account makes the password itself, keeps it, and passes it::

		password = users.generate_password()
		user_id = users.create(email, "Ann", "Wanjiru", password=password)
		# hand `password` to whoever is enrolling them, once, and keep no copy

	Calling this without a password creates a real, billed account that nobody
	can sign in to until `set_password` is called -- which is a legitimate thing
	to want (enrol now, credential on their first day) and a silly thing to do
	by accident.

	`changePasswordAtNextLogin` is on, so whatever password is used here is good
	for exactly one sign-in. That is the whole reason it is safe to speak a
	generated password aloud down a phone.

	The body of this call contains that password in plain text. Nothing logs it
	-- `client._send` says how that is arranged and how easily it would not be.
	"""
	body = {
		"primaryEmail": email,
		"name": {"givenName": given_name, "familyName": family_name},
		"password": password or generate_password(),
		"changePasswordAtNextLogin": True,
		"orgUnitPath": client.credentials().org_unit_path,
	}
	body.update(fields)

	created = client.directory("POST", "users", json_body=body)
	user_id = (created or {}).get("id")
	if not user_id:
		frappe.throw(
			_("Google created the account but returned no user id."), exc=client.GoogleWorkspaceError
		)
	return user_id


def ensure(
	email: str,
	given_name: str,
	family_name: str,
	password: str | None = None,
	**fields,
) -> str:
	"""This address's account id, creating the account if there is not one.

	Create first, look up only if that is refused. The other order -- look up,
	create if absent -- costs an extra call on the ordinary path and is still
	wrong: two requests can both find nothing and both try to create, and one of
	them gets the 409 anyway. Google's own uniqueness check is the authority on
	whether an account exists, so it is what gets asked, and the lookup is the
	recovery rather than the test.

	This matters more here than in the Auth0 section, because the thing being
	created is billed. A button pressed twice, a retried job, a document saved
	again: each of those is a duplicate account and a monthly charge if the
	answer to "does it exist" is worked out anywhere other than at Google.

	`fields` and `password` are applied only when the account is created. An
	existing account is returned as it stands and not quietly rewritten to match
	what this caller happened to pass -- overwriting somebody's name, their
	organisational unit or their password is a decision, and `update` and
	`set_password` are where it is made deliberately.

	The 409 itself does not say which account it is complaining about, only that
	there is one, so the recovery is a second lookup -- `recover_existing`, which
	is also what makes this answerable from `api` without guessing.
	"""
	try:
		return create(email, given_name, family_name, password=password, **fields)
	except client.GoogleWorkspaceError as refusal:
		if refusal.status != ALREADY_EXISTS:
			raise

	return recover_existing(email)


def recover_existing(email: str) -> str:
	"""The id of the account behind a 409, or a refusal explaining the contradiction.

	Split out of `ensure` rather than inlined into it because `api.ensure_user`
	needs the same recovery *and* needs to know it happened -- it has generated
	a password, and a password that was never applied to anything must not be
	returned to the caller as though it were a credential. Sharing the recovery
	is what lets that endpoint tell a create from a find without either
	re-implementing this or guessing from a lookup done beforehand, which a
	second request arriving in between would make wrong.

	`None` from `find` here is genuinely contradictory: Google has said in one
	breath that the address is taken and in the next that nothing holds it. The
	honest readings are the propagation delay the module docstring describes,
	with a create from seconds ago not yet readable, or an address belonging to
	a *deleted* account still inside its twenty-day restore window, which holds
	the address without answering to it. Both are worth saying out loud rather
	than returning nothing and letting a caller store an empty id.
	"""
	existing = find(email)
	if not existing:
		frappe.throw(
			_(
				"Google says an account already exists for {0}, but no account with that address"
				" could be found. Either it was created moments ago and is not readable yet, or"
				" the address belongs to a recently deleted account still inside its restore"
				" window."
			).format(email),
			exc=client.GoogleWorkspaceError,
		)
	return existing


def update(user_key: str, **fields) -> dict:
	"""Change an account, and return it as Google now holds it.

	A PATCH, so only the keys passed are touched and everything else is left
	alone -- `users.update`, Google's PUT, replaces the whole resource and is
	not what anybody means by an update.

	Two things to know, both of which read as data quietly going missing rather
	than as errors.

	*A list-valued field is replaced, not merged.* `phones`, `emails`,
	`organizations`, `externalIds`, `addresses`, `relations`: passing one entry
	removes every entry that was there. To add a phone number to somebody who
	has one, read the account, append, and send the whole list::

		account = users.get(user_id)
		phones = account.get("phones") or []
		phones.append({"value": "+254712345678", "type": "mobile"})
		users.update(user_id, phones=phones)

	This is why `emails` is a poor place to put a second address and `aliases`
	or `recoveryEmail` are the good ones. `emails` also carries the primary
	address and the aliases, so a caller that writes it from scratch is writing
	over things it did not put there.

	*Changing `primaryEmail` renames the account* and turns the old address into
	an alias rather than freeing it. That is usually wanted and is never
	reversible by simply putting the old value back.

	`recoveryEmail`, `recoveryPhone`, `suspended`, `orgUnitPath` and `name` are
	scalars or small objects and behave the way anybody would expect.
	"""
	return client.directory("PATCH", f"users/{_segment(user_key)}", json_body=fields)


def set_password(
	user_key: str,
	password: str | None = None,
	change_at_next_login: bool = True,
) -> str:
	"""Set a password on an existing account, and return the one that was set.

	The answer to the question `create` raises -- an account exists and nobody
	can sign in to it -- and the nearest thing this section has to Auth0's
	password change ticket, which is to say not very near. Auth0 hands out a URL
	that only its holder can use once; this hands back a credential that works
	for anybody who reads it, until it is used.

	So the return value is the point of the function and also its hazard. It
	goes to whoever is enrolling the person, by a channel that is not a log, a
	comment, a custom field or an email to a mailing list, and no copy is kept.
	`change_at_next_login` is what bounds the damage: the password is good for
	one sign-in and the person then chooses their own.

	Left on unless a caller says otherwise, and the one reason to say otherwise
	is a service account or a shared mailbox where there is no person to do the
	choosing.
	"""
	chosen = password or generate_password()
	client.directory(
		"PATCH",
		f"users/{_segment(user_key)}",
		json_body={"password": chosen, "changePasswordAtNextLogin": bool(change_at_next_login)},
	)
	return chosen


def suspend(user_key: str, suspended: bool = True) -> dict:
	"""Suspend an account, or restore one, and return it as it now stands.

	What offboarding usually means, and what should be reached for before
	`delete` in almost every case. A suspended account keeps its mail, its
	files, its group memberships and its address -- so nothing is lost, nobody
	else can be given the address by mistake, and restoring is this call with
	`False`.

	It does not stop the billing. A suspended account still occupies its
	licence, which is the one argument for deleting, and the one thing to have
	an explicit answer to before wiring this to anything.
	"""
	return update(user_key, suspended=bool(suspended))


def delete(user_key: str) -> None:
	"""Remove an account, or do nothing if it is already gone.

	An end state rather than an act: a caller tidying up after a record has no
	use for a 404 about an account somebody removed in the Admin console last
	month, and treating it as an error means every caller writes the same `try`
	around it. Every other refusal still raises.

	Read `suspend` first. This destroys the mailbox and the Drive contents
	unless they were transferred beforehand, which is a separate API this
	section does not wrap, and the address is held for twenty days -- not freed,
	not reusable, and not available to `ensure` -- before it can be used again.

	Deliberately not reachable over HTTP. `api` offers no wrapper for this on
	purpose; a controller that means it calls this directly, having checked a
	permission on the record it is acting for.
	"""
	try:
		client.directory("DELETE", f"users/{_segment(user_key)}")
	except client.GoogleWorkspaceError as refusal:
		if refusal.status != NOT_FOUND:
			raise


def aliases(user_key: str) -> list[str]:
	"""Every additional address this account receives mail at.

	The addresses themselves rather than Google's wrapper objects, because the
	wrapper carries an `id` that is the account's own id repeated, a `kind`, and
	an etag, and no caller has ever wanted any of those.

	Google omits the key entirely for an account with no aliases rather than
	returning an empty list, which is the sort of thing that turns into a
	`TypeError` three call sites away.
	"""
	answer = client.directory("GET", f"users/{_segment(user_key)}/aliases")
	rows = (answer or {}).get("aliases") or []
	return [row["alias"] for row in rows if isinstance(row, dict) and row.get("alias")]


def add_alias(user_key: str, alias: str) -> dict:
	"""Give this account another address at a domain the Workspace account owns.

	This is what "a second email address" means when the address is at your own
	domain, and it is not the `emails` field -- see `update` on why writing that
	is a good way to lose the aliases already there.

	Two limits worth knowing. The domain has to be one this Workspace account
	owns and has verified, or Google refuses. And the alias does not start
	working when this returns: Google's own documentation allows up to
	twenty-four hours before mail sent to it arrives, which is the propagation
	delay the module docstring describes at its most pronounced.

	A duplicate is a 409 and is raised rather than swallowed. Unlike an account,
	an alias that already exists somewhere is worth an error: it may be on
	somebody else's account, and quietly succeeding would report that this
	person now has an address that in fact belongs to a colleague.
	"""
	return client.directory("POST", f"users/{_segment(user_key)}/aliases", json_body={"alias": alias})


def remove_alias(user_key: str, alias: str) -> None:
	"""Take an address away from this account, or do nothing if it has none.

	An end state, for the same reason `delete` is one. Mail to the address stops
	being delivered, with the same delay it took to start.
	"""
	try:
		client.directory("DELETE", f"users/{_segment(user_key)}/aliases/{_segment(alias)}")
	except client.GoogleWorkspaceError as refusal:
		if refusal.status != NOT_FOUND:
			raise


def photo(user_key: str) -> dict | None:
	"""This account's photo as Google holds it, or `None` if it has none.

	The `photoData` in it is web-safe base64 and unpadded, which is not what
	`base64.b64decode` expects on either count -- `base64.urlsafe_b64decode`
	with the padding put back is how to get the bytes out.

	`None` for an account that has never had one, because Google reports that as
	a 404 against the photo rather than as an empty photo, and an absence is not
	an error.
	"""
	try:
		return client.directory("GET", f"users/{_segment(user_key)}/photos/thumbnail")
	except client.GoogleWorkspaceError as refusal:
		if refusal.status == NOT_FOUND:
			return None
		raise


def photo_format(data: bytes, mime_type: str | None = None) -> str:
	"""What Google should be told this image is, in the spelling it wants.

	Google's `mimeType` is not a media type despite the name: the values are
	`JPEG`, `PNG`, `GIF`, `BMP`, `TIFF`, `WEBP`, and `image/jpeg` is a 400. A
	caller holding a `File` on this site has a media type and nothing else, so
	both spellings are accepted and one is sent.

	Sniffed from the first few bytes when nothing is passed, which is both more
	convenient and more reliable than the media type on a `File` -- that is
	whatever the browser claimed at upload, and a PNG named `.jpg` is common
	enough to be worth not trusting.
	"""
	if mime_type:
		named = mime_type.strip()
		named = PHOTO_ALIASES.get(named.lower(), named.upper())
		if named in PHOTO_FORMATS:
			return named
		frappe.throw(
			_("Google does not accept {0} as a profile photo. It takes: {1}.").format(
				mime_type, ", ".join(PHOTO_FORMATS)
			),
			exc=client.GoogleWorkspaceError,
		)

	sniffed = _sniff(data)
	if not sniffed:
		frappe.throw(
			_("That file is not an image Google will take as a profile photo. It takes: {0}.").format(
				", ".join(PHOTO_FORMATS)
			),
			exc=client.GoogleWorkspaceError,
		)
	return sniffed


def _sniff(data: bytes) -> str | None:
	"""The image format of some bytes, from their magic number, or `None`.

	Enough of each signature to tell the six Google accepts apart and no more.
	This is not validation -- a truncated JPEG passes -- it is deciding what to
	put in one field, and Google is the one that validates.
	"""
	if data.startswith(b"\xff\xd8\xff"):
		return "JPEG"
	if data.startswith(b"\x89PNG\r\n\x1a\n"):
		return "PNG"
	if data[:6] in (b"GIF87a", b"GIF89a"):
		return "GIF"
	if data.startswith(b"BM"):
		return "BMP"
	if data[:4] in (b"II*\x00", b"MM\x00*"):
		return "TIFF"
	if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
		return "WEBP"
	return None


def set_photo(user_key: str, data: bytes, mime_type: str | None = None) -> dict:
	"""Put a profile photo on this account.

	Its own call, because there is no photo field on a user and there is no way
	to do this as part of creating one. Which makes it the clearest case of the
	propagation delay the module docstring describes: called on the line after
	`create` it fails often enough to be unreliable and rarely enough to pass
	every test, so it belongs in a job that can retry.

	The encoding is the trap. Google wants web-safe base64 -- `-` and `_` rather
	than `+` and `/` -- and `base64.b64encode` produces neither, so a photo
	encoded the obvious way is accepted for some images and rejected or mangled
	for others depending on whether the bytes happened to produce a `+`. The
	padding comes off too, which the API is relaxed about and every example of
	it omits.

	Square is what ends up displayed. Google crops to it from the centre, so a
	tall photo loses its top and bottom rather than being letterboxed.
	"""
	if not data:
		frappe.throw(_("There is no image to send."), exc=client.GoogleWorkspaceError)
	if len(data) > MAX_PHOTO_BYTES:
		frappe.throw(
			# Plain arithmetic rather than `frappe.format_value`, which reads a
			# number format off `frappe.local` and so needs a site to say how
			# big a file is.
			_("That photo is {0} MB and Google's limit is {1} MB.").format(
				round(len(data) / 1024 / 1024, 1), MAX_PHOTO_BYTES // 1024 // 1024
			),
			exc=client.GoogleWorkspaceError,
		)

	body = {
		"photoData": base64.urlsafe_b64encode(data).decode("ascii").rstrip("="),
		"mimeType": photo_format(data, mime_type),
	}
	return client.directory("PUT", f"users/{_segment(user_key)}/photos/thumbnail", json_body=body)


def remove_photo(user_key: str) -> None:
	"""Take the photo off this account, or do nothing if it has none.

	Google falls back to the letter avatar it draws from the person's name. An
	end state, for the same reason `delete` and `remove_alias` are.
	"""
	try:
		client.directory("DELETE", f"users/{_segment(user_key)}/photos/thumbnail")
	except client.GoogleWorkspaceError as refusal:
		if refusal.status != NOT_FOUND:
			raise
