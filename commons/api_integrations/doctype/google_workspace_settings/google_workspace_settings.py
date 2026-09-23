"""Where this site's Workspace domain and its service account credentials are kept.

A Single, because setting up an integration is something a System Manager does
once, in the desk, on a site they may not have shell access to -- and because a
credential that can only be changed by a deploy is a credential nobody rotates.

`service_account_key` is a `Password` field, which is not merely a masked
`Data`: the value is stored encrypted in `__Auth` rather than in this doctype's
own row, an ordinary read of the document gives back a placeholder rather than
the key, and it is not carried out by a report, by the REST API, or by a fixture
export. It is read with `get_password`, and the one place that does is
`commons.api_integrations.google_workspace.client.settings`.

A `Password` field holding two kilobytes of JSON looks odd in the form and is
right anyway. `__Auth.password` is a `TEXT` column, so it fits with room to
spare, and it is the only field type on the platform whose value is encrypted at
rest. The alternative -- a `Code` field, which would at least be pleasant to
paste into -- puts an RSA private key in `tabSingles` in plain text, in every
backup, and in front of anybody who can open this doctype. It is pasted once.

Read permission is System Manager and nobody else, and even they cannot see the
key once it is saved. That is worth preserving if a role is ever added here: the
rest of this integration is built so that no caller ever needs the credential, only
the actions it authorises. See `commons.api_integrations.google_workspace.api` on why nothing
hands a token out.

What has to be true elsewhere for this to work is in
`commons.api_integrations.google_workspace.client`: the service account's numeric client id
authorised for `client.SCOPES` in the Admin console's domain-wide delegation
screen, and the administrator named here able to manage users. Neither is
visible from this site, and getting either wrong produces the same
`unauthorized_client` -- which is why `client._issue` answers it with both
places to go and look rather than with what Google said.
"""

from frappe.model.document import Document


class GoogleWorkspaceSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		admin_email: DF.Data | None
		customer_id: DF.Data | None
		extra_scopes: DF.SmallText | None
		org_unit_path: DF.Data | None
		service_account_key: DF.Password | None
	# end: auto-generated types

	def on_update(self):
		"""Drop any cached token, because it was issued for the old settings.

		Without this, rotating the key leaves the previous token in Redis for up
		to an hour, and the change appears not to have taken effect -- or worse,
		appears to have taken effect while every call is still being made by the
		old service account.

		It matters at least as much for `extra_scopes`. A token carries the
		scopes it was minted with, so a scope added here without dropping the
		cache fails in the most confusing way available: a 403 on the very call
		that was just enabled, for up to an hour, on a site where everything
		looks correctly configured. The cache key is built from the service
		account and the administrator, so neither a changed key nor a changed
		scope would displace it on its own; see
		`commons.api_integrations.google_workspace.client.cache_key`.
		"""
		from commons.api_integrations.google_workspace import client

		client.forget_token()
