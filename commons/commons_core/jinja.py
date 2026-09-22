# Copyright (c) 2026, Peter and contributors
# For license information, please see license.txt

"""Template helpers this app adds to Jinja, that belong to no section.

Frappe builds one Jinja environment per site and every app's `jinja` hook adds
to it, so what is here is reachable from every print format, letter head,
notification, email template and portal page on the site -- including ones
written by somebody who has never heard of this app. That reach is the reason
this file is small and expects to stay that way: a helper only earns a line in
the hook if it is useful to a template that has nothing to do with the section
it came from.

Helpers that *are* about a section stay with it, and are named individually in
the same hook -- `commons.statement.api.party_statement` is one. The test is the
usual one: a template calling `party_statement` is asking this app a question
about a party, and a template calling `make_qr_code` is only asking for an
image.

Here rather than at the app root because "belongs to no section" is what this
module is for, and it is the same test stated the other way round: a helper that
would make sense in an app with none of this one's sections is one of Frappe's
own facilities being extended, which is `commons_core`. The name the hook
exposes is the function's, not the module's, so moving the file changed nothing
for the print formats already calling it.

`make_qr_code` came from the retired NepalERP app, where it was the whole of
what that app gave to Jinja. Print formats on live sites call it by that bare
name, so the name and the return value are both fixed by the templates already
written against them -- see the note on the return type below.
"""

import base64
import io

import qrcode


def make_qr_code(data: str = "") -> str:
	"""Return `data` as a QR code, as a PNG `data:` URI ready for an `<img src>`.

	A `data:` URI rather than a File is deliberate. The caller is a template
	being rendered, usually for a PDF, and usually for a document whose QR code
	encodes something about that document -- so a File would mean a row and a
	blob on disk per render, for an image that is wanted exactly once and is
	cheaper to regenerate than to look up. The cost is that the URI is inlined
	into the rendered HTML at roughly a third again the size of the PNG, which
	for the few hundred bytes a QR code takes is not a cost worth avoiding.

	This is not whitelisted, and the version in the retired app was. Nothing
	called it over HTTP -- no client script, no portal page -- and whitelisting
	it would leave the site with an endpoint that turns caller-supplied text
	into an image for anybody with a session, which is a thing to answer for
	without a caller that needs it.
	"""
	stream = io.BytesIO()
	qrcode.make(data).save(stream)
	encoded = base64.b64encode(stream.getvalue()).decode()

	return f"data:image/png;base64,{encoded}"
