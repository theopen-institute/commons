"""Bank reconciliation: statement lines, and the vouchers that account for them.

The page is `frontend/src/pages/BankReconciliation.vue`. Nearly everything it
does is ERPNext's own: it lists `Bank Transaction`s through the document API
and it matches, creates payment and journal entries, updates and unlinks through
the whitelisted functions `bank_reconciliation_tool.py` and `bank_transaction.py`
already ship. The desk tool's *functions* were never the problem; the form they
hang off was.

What this package adds is booking a deposit as a loan repayment from the page.
It makes the `Loan Repayment` a person would make in the desk and matches it to
the deposit in the same request. See `reconciliation.create_loan_repayments`.
"""
