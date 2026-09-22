"""Where this site's Auth0 tenant and its Management API credentials are kept.

A Single, because setting up an integration is something a System Manager does
once, in the desk, on a site they may not have shell access to -- and because a
credential that can only be changed by a deploy is a credential nobody rotates.

`client_secret` is a `Password` field, which is not merely a masked `Data`: the
value is stored encrypted in `__Auth` rather than in this doctype's own row, an
ordinary read of the document gives back a placeholder rather than the secret,
and it is not carried out by a report, by the REST API, or by a fixture export.
It is read with `get_password`, and the one place that does is
`commons.auth0.client.settings`.

Read permission is System Manager and nobody else, and even they cannot see the
secret once it is saved. That is worth preserving if a role is ever added here:
the rest of this section is built so that no caller ever needs the credential,
only the actions it authorises. See `commons.auth0.api` on why nothing hands a
token out.

The scopes to grant the machine-to-machine application in the Auth0 dashboard
are the ones the actions in use require -- `create:users` and `read:users` to
make accounts (both, for the reason `commons.auth0.users.ensure` gives),
`update:users` to change them, `delete:users` to remove them.
"""

from frappe.model.document import Document


class Auth0Settings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		audience: DF.Data | None
		client_id: DF.Data | None
		client_secret: DF.Password | None
		connection: DF.Data | None
		domain: DF.Data | None
	# end: auto-generated types

	def on_update(self):
		"""Drop any cached token, because it was issued for the old credentials.

		Without this, rotating the client secret leaves the previous token in
		Redis for up to a day, and the change appears not to have taken effect
		-- or worse, appears to have taken effect while every call is still
		being made as the old application. The cache key is built from the
		domain and client id, so a changed secret alone would not displace it;
		see `commons.auth0.client.cache_key`.
		"""
		from commons.auth0 import client

		client.forget_token()
