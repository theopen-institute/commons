# Department procurement budgets

Department Budget enforces a single annual procurement allocation per company,
department and fiscal year, independently of ERPNext's expense-account budgets.
Finance (Accounts Manager or System Manager) creates and maintains allocations in
Desk. Original allocations and existing adjustments cannot be rewritten; append a
reasoned adjustment or reversing adjustment instead. Budget changes are versioned.

## Accounting policy

- Company currency, **net item amounts excluding taxes**, freight posted as taxes,
  and other invoice-level charges. Foreign purchases use ERPNext's base net amount.
- Spent means submitted Purchase Invoice item value, including stock and equipment.
  It is not cash paid or GL expense. Journals, expense claims, payroll, depreciation,
  and inventory consumption are outside this procurement budget.
- Final approval reserves the request's verified rate, falling back to its estimate.
  Every approved line needs a positive estimate. The approved valuation is frozen.
- A Material Request does not create another monetary reservation. Its existing
  committed-quantity fields still describe fulfillment only.
- Purchase orders replace the corresponding portion of request reservations.
  Invoices replace the corresponding portion of order commitments. Partial
  quantities and different UOMs are supported. Direct invoices against Material
  Requests replace the request reservation directly.
- Cancelling an invoice restores the order commitment. Cancelling an order restores
  the still-approved request reservation. Closing an order also restores unfulfilled
  request reservations: closing an order does **not** withdraw the original approval.
  To abandon a request, cancel its downstream documents before cancelling it.
- Credit notes reduce spent and restore the associated outstanding commitment (or
  reservation). They must identify original invoice items. Close the order when
  replacement purchasing is no longer intended.
- A linked purchase retains the original request's budget year; direct purchases use
  their transaction/posting date. There is no automatic rollover or parent-department
  pooling. Use separate purchasing documents for different department/year budgets.
- Budget Department on direct PO/PI item rows is mandatory at submission. Linked
  rows inherit their budget through request/order/receipt/invoice references. This
  budget attribution does not replace ERPNext Cost Center/accounting dimensions.

## Setup and existing documents

1. Run `bench --site SITE migrate`, then build the frontend with `npm run build`
   inside `frontend`. Restart long-running production processes normally.
2. Create each Department Budget in Desk with company, department, fiscal year,
   owner, and annual allocation. Leave **Opening balances reconciled** unchecked.
3. Finance must review all spending and outstanding purchasing for that department
   and year. Attribute direct legacy purchases explicitly. Never assume the balance
   starts at zero simply because the feature was newly installed.
4. Register reviewed submitted source documents using the administrative helper
   `tbs_commons.budget.register_existing_documents`. Its `documents` argument is a
   list of `{ "doctype": "Procurement Request", "name": "..." }` objects. Supply
   requests first, then orders, invoices, and credit notes. Include completed
   requests whose purchases still contribute to this year's spend. Submit one
   complete batch: the final exposure must fit within the allocation. The batch
   rolls back on failure. Repeating an unchanged document creates no extra entry.
   Historical requests need reviewed positive valuations: historical approval
   amounts cannot be reconstructed if they were never recorded. Direct historical
   purchases must have their budget department assigned by a reviewed data migration.
5. Review Department Budget Position and Department Budget Movement, then check
   **Opening balances reconciled**. Until then, new approvals and purchasing against
   the budget are refused. Missing budgets also block approval.

No allocations, historical values, or department assignments are guessed or seeded.
The owner is administrative metadata; approval authority remains with the existing
Procurement Request workflow. There is no ordinary approver override. Finance can
increase an allocation with an audited adjustment.

## Enforcement and visibility

Document hooks cover Procurement Request submission/cancellation, Purchase Order
and Purchase Invoice submission/cancellation/amendment updates. A Purchase Order
mixin additionally covers ERPNext's close/reopen method, which bypasses save hooks.
A refusal rolls back the document and its accounting writes in the same transaction.

Each writer locks the budget row and reads its positions with `FOR UPDATE` before
checking availability. Positions hold source valuations; append-only movement
records contain portfolio deltas plus before/after source snapshots. Source keys
are unique, and unchanged retries are idempotent. Downstream sources cannot be
orphaned by cancelling their upstream document. Never update submitted purchasing
rows with raw SQL or `db_set` in another integration; those bypass document hooks.

Approvers see allocation, spent, reserved, outstanding orders, availability, request
amount and availability after approval. Desk shows the balance as well. Monetary
shortfalls are returned by the backend. Previews refresh after approval attempts.
Department summaries require the named approver's submit permission or a finance/
purchase-manager role, plus read access to the request. Supporting-document links
are filtered by each source document's read permissions.

For reconciliation, compare positions with their linked submitted documents and
movement snapshots; positions are the controlled financial projection, not a GL
ledger. Raw-SQL changes and historical imports outside these hooks require explicit
reconciliation. A periodic automated GL reconciliation is not included because
these figures intentionally use procurement values rather than GL expenses.

## Verification

- `python -m unittest tbs_commons.test_budget_math` tests stage replacement, partial
  quantities, credit notes, cancellation, direct purchases and closure arithmetic.
- `bench --site SITE execute tbs_commons.test_budget_integration.run` runs actual
  request, PO, PI, credit-note and database tests, then rolls all fixtures back.
  It isolates budget hooks from workflow validation; the existing workflow itself
  is unchanged. It checks the mixin path, missing/unreconciled budgets, hard limits,
  frozen approvals, adjustment restrictions and cancellation reversals.
- Frontend: `npm run type-check` and `npm run build`.
