# Department budgets

An annual allocation per company, department and fiscal year, enforced when a
Material Request is submitted. It is a departmental management control, separate
from ERPNext's own **Budget** doctype: it is held against Department rather than
a Cost Center and expense account, and it does not read or post to the General
Ledger or the Stock Ledger.

## The allocation

**Department Budget** is submittable, and only a *submitted* budget authorises
anything. A draft is visible in procurement feedback but will not let a Material
Request be charged to it. Only one submitted budget may cover a department at any
given date.

The allocation amount is fixed once submitted. To restate it, **cancel the budget
and amend it**. Nothing has to be carried across: a budget declares an amount for a
department and a period, it does not own the requests, so the replacement sees the
usage that period already carries. An amendment may change the amount only —
keeping the same company, department and fiscal year is enforced, as is the rule
that the new amount cannot be below what is already charged.

## What counts as usage

The tally is **submitted Material Requests** of type **Purchase** or **Material
Issue**, valued at quantity × the request's own entered rate, in company currency.

Neither usage nor attribution is stored. A request belongs to whichever allocation
covers its **department** on its **transaction date**, and the total is summed
from the request rows themselves. Both consequences are worth knowing: the tally
cannot drift from the documents it describes, so there is nothing to reconcile and
no import step beyond attribution; and no Material Request links to a Department
Budget, so restating one moves no data and rewrites no request.

- **Allocation** = the budget's annual amount.
- **Used** = quantity × rate over submitted Purchase/Material Issue requests.
- **Available** = allocation − used. This is the hard backend limit.
- **Outstanding procurement (provisional)** = estimated value not yet covered by
  submitted requests, across Pending, Under Review, Approved and Completed
  Procurement Requests in the department and fiscal year.
- **Projected available** = available − provisional, including the displayed
  request once if it is still a draft. Other users' drafts, rejections and
  cancellations are excluded.

Purchase Orders, Purchase Receipts, Purchase Invoices, credit notes, Stock Entries,
payments, GL postings and stock valuation changes have **no effect**. Other request
purposes, such as Material Transfer or Manufacture, are outside the tally. Two
separately submitted requests both count even if they concern the same goods.

## Document lifecycle

A draft request consumes nothing. Submission charges its entered value, which may
differ from the Procurement Request estimate. Cancelling it releases the charge —
there is no reversing entry to write, because a cancelled request simply stops
matching the tally. Amendments follow cancellation and new submission.

A submitted request continues to count when Stopped, Ordered, Issued or fulfilled.
Stopping one does not release budget: cancel and amend it to revise the amount.
Submitted rates, quantities, date, type, department and source references cannot
be edited, and a price-list refresh will not revalue them.

Procurement Request approval creates no reservation and can proceed without a
budget or with negative projected availability. Material Request submission is the
point at which a submitted allocation and available funds are required.

## Rates, currency and attribution

Both request types use their entered rate; stock valuation is neither consulted nor
overwritten, so budget usage can legitimately differ from inventory value and
invoiced expenditure. Rates and amounts are company-currency fields, recomputed
server-side at the stored precision. Use a buying price list in company currency,
so the native price lookup cannot put an unconverted foreign price into them.
There are no separate tax or freight adjustments.

Requests inherit the department from validated Procurement Request row references.
Direct requests require **Department** to be set on the Material Request. Linked and
explicitly selected departments must agree; use separate requests for different
departments.

That field is this app's, added to the Material Request header, and is singular on
purpose: one request charges one department's budget. It is not ERPNext's accounting
dimension — enabling a Department dimension adds a separate per-row `department` to
*Material Request Item*, which is accounting attribution and plays no part in this tally.

The **request's transaction date** chooses the allocation, even when its Procurement
Request originated in another year. There is no rollover or parent-department pooling.

## Enforcement and history

Each writer locks the Department Budget row and reads the tally with a locking read
before checking it, so concurrent submissions cannot both fit into the same
remaining balance. A refusal rolls the request submission back with it.

History is the documents' own:

- `docstatus` and `amended_from` on the Material Request,
- the Material Request **Version** log, which this app switches on (ERPNext ships
  it off) — it records every field change and every docstatus transition, with
  user and timestamp,
- the Department Budget amendment chain, which records each restatement and the
  move of requests onto it.

Note the one thing this does not survive: deleting a cancelled Material Request
outright erases its budget history along with it.

A period with no submitted allocation simply has no tally. Cancelling a budget
without replacing it does not delete or detach anything — the requests keep their
department and date, and are counted again as soon as an allocation covers them.

## Upgrading a site that already has allocations

Department Budget became submittable. Rows created before that change carry
`docstatus = 0`, and a draft authorises nothing — so on such a site **every**
Purchase/Material Issue submission will be refused until its allocation is
submitted. There is deliberately no automatic patch for this: submitting a
document on the user's behalf is Finance's decision, not a migration's.

Review and submit each existing allocation after upgrading:

```
bench --site SITE console
>>> import frappe
>>> frappe.get_all("Department Budget", filters={"docstatus": 0},
...                fields=["name", "company", "department", "fiscal_year", "annual_amount"])
```

Submit the ones that are current; leave or delete the rest. A site with no
Department Budget rows needs nothing.

## Historical attribution

Submitted requests that already carry a department are counted the moment an
allocation covers their date. Only requests with no department need importing, and
importing means attributing them:

```
tbs_commons.procurement.budget.register_existing_documents
```

Its `documents` argument is a list such as
`[{"doctype": "Material Request", "name": "MAT-MR-...", "department": "..."}]`.
The department is required only where the request has none, must agree with any
linked Procurement Request, and is never guessed. Only submitted Purchase/Material
Issue requests are accepted. The import is idempotent, and the batch's final usage
must fit the allocation — if it does not, amend the budget upward first.

Requests with zero or missing rates need Finance review and correction through an
amendment. Raw SQL or `db_set` changes bypass the document hooks that enforce all
of this.

## Verification

- `python -m unittest tbs_commons.procurement.test_budget_math` — provisional estimate arithmetic.
- `bench --site SITE execute tbs_commons.procurement.test_budget_integration.run` —
  real Purchase and Material Issue requests, hard limits, cancellation, budget
  amendment, partial fulfilment, UOMs, immutability, historical attribution and
  PO/PI independence. Fixtures are rolled back.
- Frontend: `npm run type-check` and `npm run build` in `frontend`.
