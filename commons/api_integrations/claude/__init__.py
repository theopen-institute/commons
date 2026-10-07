"""Claude, Anthropic's model: the key, the call, and reading a document.

Like the other integrations here, a library and not a feature. It knows nothing
about any doctype. It takes a scan and a JSON schema and gives back what the
scan says, in that shape. Which schema, which scan, and what becomes of the
answer are decided by whatever calls it -- today that is
`commons.document_capture`, which drafts Purchase Invoices and Expense Claims
from what comes back, and `commons.banking.statement_import`, which reads a
bank statement into rows.

What is here
------------
`client` is the way in: the API key and model off `Claude Settings`, and one
function, `create_message`, that makes the call and turns every refusal into a
`ClaudeError` a person can read, with `stream_message` for the same call from a
background job. `documents` is the operation built on it: `read`, which
prepares an image or a PDF and asks for it back as JSON, and `jobs` runs a
reading in the background and reports its progress.

What a prompt says about this site's documents -- the company's country and
currency, the calendar, the local tax terms, the site's own instructions -- is
not here, because it reads Company, Commons Settings and Document Capture
Settings. It is `commons.document_capture.locale`, which bank statement import
uses too. `Claude Settings` holds the key and the model, nothing else.

There is no `api` module, because nothing about this integration is useful to a
browser on its own. A whitelisted "read this file" would be a way to spend the
site's API credit on anything at all, so the endpoints live with the features
that call `read`, behind those features' own permission checks.

The key is held the way every credential in this module is: a `Password` field,
read by `client.settings` and returned by nothing.
"""
