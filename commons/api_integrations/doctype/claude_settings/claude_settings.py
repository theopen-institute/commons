"""Where this site's Claude API key is kept, and which model it calls.

A Single, like every settings doctype in this module, so a System Manager can
set or rotate the key in the desk without a deploy.

`api_key` is a `Password` field, so it is stored encrypted in `__Auth`, is
never shown again once saved, and is left out of the REST API, reports and
fixture exports. The one place that reads it is
`commons.api_integrations.claude.client.settings`, and nothing whitelisted
returns it.
"""

from frappe.model.document import Document


class ClaudeSettings(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		api_key: DF.Password | None
		model: DF.Data | None
	# end: auto-generated types

	pass
