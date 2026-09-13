# Budget modes

Create allocations in the standard **Budget** DocType. **Budget Mode** has two values:

- **Account** (default): standard ERPNext account/dimension validation, distributions,
  and configured MR/PO/actual-expense controls. Accounts must still be leaf accounts;
  selecting the Expenses group is not supported.
- **Cumulative Material Requests**: one company, leaf department and fiscal year,
  without an account. The annual limit and append-only adjustments use the MR tally
  described below. Submit the Budget before activating reconciliation.

The mode is fixed after the first save. A cumulative Budget with MR audit history
cannot be cancelled or revised; use adjustments or turn off reconciliation to
block further submissions. Draft allocations never authorize MR submission.

The installer creates/reuses the Department accounting dimension. Cumulative
records carry Department for compatibility with native budget readers, but have
no account, no accounting distribution, and all native applicability switches off.
The standard Budget Variance Report shows account budgets only; cumulative totals
are shown on the Budget form and in procurement/MR feedback.

A cumulative allocation for the MR department and period takes precedence, even
while draft or unreconciled. Otherwise, if the company has submitted Account-mode
budgets for that period, ERPNext handles account/dimension matching and enforcement.
The frontend identifies Account mode without displaying invented department totals.
Explicit Budget Department is copied to MR item accounting dimensions in Account
mode, with conflicts rejected. If neither mode is configured, the existing missing
allocation safeguard still blocks submission.

## Cumulative MR basis

The authoritative budget tally is **submitted Material Requests**, with purpose
**Purchase** or **Material Issue**. Both use the MR's entered rate in company
currency. This is a departmental management tally; Material Requests do not post
ERPNext General Ledger or Stock Ledger entries.

## Totals and document lifecycle

- **Allocation** = Budget amount + audited adjustments.
- **Used** = sum of quantity × rate on submitted Purchase/Material Issue requests.
- **Available** = allocation − used. This is the hard backend limit.
- **Outstanding procurement (provisional)** = the estimated value still uncovered
  by submitted Purchase/Material Issue requests, across Pending, Under Review,
  Approved and Completed Procurement Requests in the department and fiscal year.
- **Projected available** = available − provisional procurement, including the
  displayed request once if it is still a draft. Other users' private drafts are
  excluded. Rejected and cancelled requests are excluded.

Procurement Request approval creates no budget reservation or ledger movement.
It can proceed without a budget or when projected availability is negative.
The frontend reports these conditions as forecasts; MR submission is the
point at which the backend requires a reconciled allocation and available funds.

A draft MR consumes nothing. Submission charges its own entered value, which may
be different from the Procurement Request estimate. Partial submissions remove
only the covered quantity from the provisional estimate. UOM conversions are
applied to coverage, not to the value already expressed as MR quantity × rate.
Cancelling the MR reverses its charge and restores the associated outstanding
procurement estimate. Amendments follow cancellation and new submission.

A submitted MR continues to count when Stopped, Ordered, Issued or fulfilled.
Stopping a request does not release budget: cancel and amend it to revise the
recorded amount. Submitted rates, quantities, date, type, department and source
references cannot be edited or refreshed from a price list. There is no partial
release based on downstream fulfillment at this stage.

Purchase Orders, Purchase Receipts, Purchase Invoices, credit notes, Stock Entries,
payments, GL postings and stock valuation changes have **no effect** on this tally.
Other MR purposes, such as Material Transfer or Manufacture, are outside it.
Two separately submitted MRs both count even if they concern the same goods;
linking a purchase and a later stock issue does not automatically net them out.

## Rates, currency, attribution and fiscal year

Both Purchase and Material Issue requests use their entered MR rate. Stock
valuation is not consulted or overwritten. A later stock issue valuation or
invoice price does not retrospectively change the MR charge. Budget usage can
therefore legitimately differ from inventory value and invoiced expenditure.

MR rate and amount are company-currency fields. Every submitted budgeted MR row
needs a positive rate and quantity. The server recalculates row amounts using
field precision. Use a buying price list in company currency; this prevents the
native MR price lookup from putting an unconverted foreign price into these
fields. Enter converted estimates explicitly when needed. There are no separate
tax or freight adjustments in the tally: only entered MR item values count.

MRs inherit the department from validated Procurement Request row references.
Direct MRs require Budget Department. Linked and explicitly selected departments
must agree; use separate MRs for different departments. Company consistency and
valid approved source rows are checked in the backend.

The **MR transaction date** chooses the fiscal year's allocation, even when its
Procurement Request originated in another year. Provisional Procurement Requests
are grouped by their own request date and reduced by linked submitted MRs across
years. There is no automatic rollover or parent-department pooling.

## Enforcement and audit

Material Request document hooks validate values, record submission and cancellation,
and reject edits to submitted budget values. A Material Request mixin prevents
ERPNext's price-list updater from revaluing submitted requests. Desk, APIs and
imports using the document lifecycle all pass through these controls.

Each writer locks the standard Budget row and reads its MR positions using
`FOR UPDATE` before checking the increase. A refusal rolls back MR submission
and the budget writes together. Unchanged retries do not create another charge.

Department Budget Position holds the submitted source snapshot. Department Budget
Movement records MR Usage Change with before/after snapshots, including cancellation
reversals. Neither Procurement Requests nor purchasing documents create positions.
Read-only finance access permits inspection without normal edit permissions.
Budget adjustments are append-only and cannot reduce allocation below actual MR
usage. Provisional Procurement Requests do not constrain adjustments.

The frontend and Procurement Request Desk form show actual MR usage and a separate
provisional estimate. The Material Request Desk form shows its own charge and the
available balance. Supporting links are limited to MRs the user can read.

## Migration and historical requests

Run `bench --site SITE migrate`, build with `npm run build` in `frontend`, and
restart production processes through the normal deployment procedure.

Existing Department Budget allocations are migrated to submitted standard Budgets
in Cumulative Material Requests mode. MR links, positions and movements are
reassigned; adjustments are copied. The original Department Budget documents remain
read-only archives with links to the new Budgets. Repeated migrations do not
duplicate allocations or charges. No new Department Budget records are needed.

The change-of-basis patch retains the old Procurement Request/PO/PI ledger as
history but excludes it from all current totals. Existing budgets are marked
unreconciled once. PO/PI budget fields are retained, hidden, for historical data;
they no longer enforce or contribute to this custom budget.

Finance should:

1. Create/review each company, department and fiscal year's allocation in **Budget**,
   choose **Cumulative Material Requests**, and submit it with reconciliation disabled.
2. Review all existing submitted Purchase and Material Issue requests for that
   department/year. Attribute direct historical MRs explicitly; unassigned MRs
   cannot be inferred to belong to a department.
3. With the budget inactive, import reviewed MRs using
   `tbs_commons.budget.register_existing_documents`. Its `documents` argument is a
   list of objects such as
   `{"doctype": "Material Request", "name": "MAT-MR-..."}`. For an unassigned
   historical MR, optionally supply `"department": "..."`. This assignment must
   agree with any linked Procurement Request. No prices or assignments are guessed.
   Only submitted Purchase/Material Issue requests are accepted. The import is
   idempotent and the batch's final usage must fit within the allocation.
4. Check **Submitted Material Requests Reconciled**. Activation checks that known
   submitted MRs for the department have matching registered positions. Missing
   or stale positions must be reconciled first.

Missing/unreconciled budgets block Material Request submission only. They do not
block Procurement Request approval. Existing submitted MRs with zero/missing rates
need Finance review and correction through an appropriate migration/amendment.
Raw SQL or `db_set` changes outside this service bypass document hooks and require
explicit reconciliation.

## Verification

- `python -m unittest tbs_commons.test_budget_math` verifies MR-only arithmetic
  and provisional partial coverage.
- `bench --site SITE execute tbs_commons.test_budget_integration.run` exercises
  real Purchase and Material Issue requests, hard limits, cancellation, partial
  fulfillment, UOMs, immutability, historical reconciliation, and PO/PI independence.
  Fixtures are rolled back. Workflow validation is isolated in these tests;
  the existing approval workflow is unchanged.
- Frontend: `npm run type-check` and `npm run build`.
