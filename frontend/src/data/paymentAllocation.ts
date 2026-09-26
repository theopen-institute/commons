import { money } from './reconciliationRules'

/**
 * Which invoices a payment from a statement line is booked against.
 *
 * Pure, and tested (`paymentAllocation.test.ts`). `reconciliation.ts` fetches
 * the party's outstanding documents with ERPNext's own
 * `get_outstanding_reference_documents`, the call behind the desk's "Get
 * Outstanding Invoices"; this proposes and checks the allocation; the payment
 * entry tab shows it and lets the bookkeeper change it.
 *
 * What is proposed, in order:
 *
 * 1. One document whose outstanding amount is exactly the payment: almost
 *    always the invoice being paid.
 * 2. Otherwise the oldest first, by due date and then posting date, until the
 *    payment runs out, which is how ERPNext's own form allocates.
 *
 * Whatever is not allocated goes on the payment as unallocated, an advance
 * the party can use against a later invoice.
 */

/** One outstanding document, as `get_outstanding_reference_documents` answers. */
export interface OutstandingDocument {
  voucher_type: string
  voucher_no: string
  posting_date: string | null
  due_date: string | null
  invoice_amount: number
  outstanding_amount: number
  currency: string | null
  bill_no?: string | null
  payment_term?: string | null
  exchange_rate?: number
  account?: string | null
}

/** The key an allocation is held under: an invoice split into payment terms
 *  comes back once per term. */
export function documentKey(document: OutstandingDocument): string {
  return `${document.voucher_type}:${document.voucher_no}:${document.payment_term ?? ''}`
}

function byAge(a: OutstandingDocument, b: OutstandingDocument): number {
  return (
    (a.due_date ?? a.posting_date ?? '').localeCompare(b.due_date ?? b.posting_date ?? '') ||
    (a.posting_date ?? '').localeCompare(b.posting_date ?? '')
  )
}

/** What to allocate to begin with: see the module comment. */
export function proposeAllocation(documents: OutstandingDocument[], amount: number): Record<string, number> {
  const payable = documents.filter((document) => document.outstanding_amount > 0)
  const exact = payable.filter((document) => money(document.outstanding_amount) === money(amount))
  if (exact.length === 1) return { [documentKey(exact[0])]: money(amount) }
  return allocateOldestFirst(payable, amount)
}

export function allocateOldestFirst(documents: OutstandingDocument[], amount: number): Record<string, number> {
  const allocation: Record<string, number> = {}
  let left = money(amount)
  for (const document of [...documents].filter((d) => d.outstanding_amount > 0).sort(byAge)) {
    if (left <= 0) break
    const take = Math.min(left, money(document.outstanding_amount))
    allocation[documentKey(document)] = money(take)
    left = money(left - take)
  }
  return allocation
}

export interface AllocationCheck {
  total: number
  /** Left on the payment as unallocated: an advance. */
  unallocated: number
  errors: string[]
}

export function checkAllocation(
  documents: OutstandingDocument[],
  allocation: Record<string, number>,
  amount: number,
): AllocationCheck {
  const errors: string[] = []
  let total = 0
  for (const document of documents) {
    const allocated = money(allocation[documentKey(document)] ?? 0)
    if (!allocated) continue
    if (allocated < 0) errors.push(`${document.voucher_no} has a negative amount`)
    if (allocated > money(document.outstanding_amount)) {
      errors.push(`${document.voucher_no} is allocated more than its outstanding amount`)
    }
    total = money(total + allocated)
  }
  const unallocated = money(amount - total)
  if (unallocated < 0) errors.push('The allocations come to more than the payment')
  return { total, unallocated, errors }
}

/** The payment entry's references rows, in the shape ERPNext's form fills. */
export function referenceRows(documents: OutstandingDocument[], allocation: Record<string, number>) {
  return documents
    .filter((document) => money(allocation[documentKey(document)] ?? 0) > 0)
    .map((document) => ({
      reference_doctype: document.voucher_type,
      reference_name: document.voucher_no,
      due_date: document.due_date,
      bill_no: document.bill_no ?? undefined,
      payment_term: document.payment_term ?? undefined,
      total_amount: document.invoice_amount,
      outstanding_amount: document.outstanding_amount,
      allocated_amount: money(allocation[documentKey(document)]),
      exchange_rate: document.exchange_rate ?? 1,
      account: document.account ?? undefined,
    }))
}
