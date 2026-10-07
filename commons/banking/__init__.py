"""Banking and the books behind it: the reconciliation page, and the accounting
fixes and audits that grew up around it.

The page is `frontend/src/pages/BankReconciliation.vue` in the SPA and, through
`frontend/src/screens/BankReconciliationScreen.vue`, the desk island the
`commons_banking` Page draws. Nearly everything it does is ERPNext's own
whitelisted functions; what it adds is here:

- `reconciliation` -- the page's own calls: booking a deposit as loan
  repayments, submitting and matching a draft voucher in one step.
- `statement_import` -- a bank statement read into Bank Transaction rows.

Around the books:

- `payroll_lines` and `payroll_payments` -- a payroll accrual one line per
  employee, and one Payment Entry per employee against the run.
- `payable_party` -- a payment's party on its tax and deduction lines.
- `internal_transfers` -- journal entries that move no money at the bank,
  cleared on their own date.
- `loan_own_dates` -- lending vouchers posted on their own dates.
- `financial_statements` -- fiscal-year columns and hidden internal accounts on
  ERPNext's financial statements.

Reports (`report/`):

- `ledger_audit` and `netted_payments` -- the Payment Ledger Audit.
- `loan_dates` -- the Loan Date Audit.
- `open_items` -- Open Receivables and Open Payables.
"""
