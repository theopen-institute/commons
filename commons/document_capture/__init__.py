"""Document capture: a scan in, a draft document out, with the scan attached.

The page is `frontend/src/pages/DocumentCapture.vue`. It takes two kinds of
scan: a supplier's invoice, which becomes a Purchase Invoice
(`purchase_invoice`), and an employee's receipts, which become their own
Expense Claim (`expense_claim`). Each is offered only where its app is
installed and the person may make one.

The shape, which the next document type should follow as well:

1. Every scan becomes a `Captured Document` first, whether it was uploaded on
   the page or emailed to an account that appends to that doctype. A
   background job asks Claude to read it (`commons.api_integrations.claude`)
   and stores what comes back on the record. If the read fails, the scan is
   kept, with the reason, to be read again. See `capture`.
2. The reader checks and corrects a draft in a dialog, beside the scan. What
   the reading most likely means on this site (which supplier, which
   company, which accounts) is worked out when it is opened, as far as that
   person may see. The figures on screen are ERPNext's own.
3. `create` inserts the document as a draft, attaches the scan to it, and
   marks the capture drafted, in one transaction.

Nothing here submits a document. What comes out is a draft for somebody to
check against the scan and submit in the desk, the same as a draft typed by
hand.

A module of its own, in `modules.txt`, because it owns a doctype: see
`commons.commons_core` on what earns one.
"""
