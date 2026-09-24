"""Claude, Anthropic's model: the key, the call, and reading a document.

Like the other integrations here, a library and not a feature. It knows nothing
about any doctype. It takes a scan and a JSON schema and gives back what the
scan says, in that shape. Which schema, which scan, and what becomes of the
answer are decided by whatever calls it -- today that is
`commons.document_capture`, which drafts a Purchase Invoice from what comes
back.

What is here
------------
`client` is the way in: the API key and model off `Claude Settings`, and one
function, `create_message`, that makes the call and turns every refusal into a
`ClaudeError` a person can read. `documents` is the one operation built on it so
far: `read`, which prepares an image or a PDF and asks for it back as JSON.

There is no `api` module, because nothing about this integration is useful to a
browser on its own. A whitelisted "read this file" would be a way to spend the
site's API credit on anything at all, so the endpoints live with the features
that call `read`, behind those features' own permission checks.

The key is held the way every credential in this module is: a `Password` field,
read by `client.settings` and returned by nothing.
"""
