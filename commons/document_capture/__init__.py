"""Document capture: a scan in, a draft document out, with the scan attached.

The page is `frontend/src/pages/DocumentCapture.vue`. Purchase invoices are the
first document it takes, and `purchase_invoice` is everything behind them.

The shape, which the next document type should follow as well:

1. The browser sends the scan to a `read_*` endpoint here. Nothing is stored.
   The endpoint asks Claude to read it (`commons.api_integrations.claude`)
   and puts the answer next to this site's own records: which supplier, which
   company.
2. The reader checks and corrects a draft in a dialog. Suggestions that depend
   on their choices, such as accounts and taxes, come from a `suggest`
   endpoint, and a `preview` endpoint has ERPNext compute the totals, so the
   figures on screen are ERPNext's own.
3. `create` inserts the document as a draft, and the browser then attaches the
   scan through Frappe's own upload, which checks write permission on the new
   document. This is the order expense claim receipts use, and for the same
   reason: a scan that is abandoned leaves nothing behind on the site.

Nothing here submits a document. What comes out is a draft for somebody to
check against the scan and submit in the desk, the same as a draft typed by
hand.

A package without a module of its own, because it owns no doctype: see
`commons.commons_core` on what earns one.
"""
