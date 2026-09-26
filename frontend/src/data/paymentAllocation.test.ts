import { describe, expect, it } from 'vitest'
import {
  allocateOldestFirst,
  checkAllocation,
  documentKey,
  proposeAllocation,
  referenceRows,
  type OutstandingDocument,
} from './paymentAllocation'

function invoice(no: string, outstanding: number, due: string, total = outstanding): OutstandingDocument {
  return {
    voucher_type: 'Sales Invoice',
    voucher_no: no,
    posting_date: due,
    due_date: due,
    invoice_amount: total,
    outstanding_amount: outstanding,
    currency: 'NPR',
  }
}

const OLD = invoice('SINV-1', 3000, '2026-05-01')
const NEW = invoice('SINV-2', 5000, '2026-06-01')
const key = documentKey

describe('proposeAllocation', () => {
  it('takes the one invoice whose outstanding is exactly the payment', () => {
    expect(proposeAllocation([OLD, NEW], 5000)).toEqual({ [key(NEW)]: 5000 })
  })

  it('otherwise allocates oldest due first until the payment runs out', () => {
    expect(proposeAllocation([NEW, OLD], 4000)).toEqual({ [key(OLD)]: 3000, [key(NEW)]: 1000 })
  })

  it('falls back to oldest first when two invoices match exactly', () => {
    const twin = invoice('SINV-3', 3000, '2026-07-01')
    expect(proposeAllocation([twin, OLD], 3000)).toEqual({ [key(OLD)]: 3000 })
  })

  it('leaves out credit notes and anything with nothing outstanding', () => {
    expect(proposeAllocation([invoice('SINV-R', -500, '2026-04-01'), OLD], 3000)).toEqual({ [key(OLD)]: 3000 })
  })
})

describe('allocateOldestFirst', () => {
  it('leaves the rest unallocated when the invoices run out first', () => {
    expect(allocateOldestFirst([OLD], 4000)).toEqual({ [key(OLD)]: 3000 })
  })
})

describe('checkAllocation', () => {
  it('counts what is left as an advance', () => {
    expect(checkAllocation([OLD, NEW], { [key(OLD)]: 3000 }, 4000)).toEqual({ total: 3000, unallocated: 1000, errors: [] })
  })

  it('refuses more than an invoice owes, or more than the payment', () => {
    expect(checkAllocation([OLD], { [key(OLD)]: 3500 }, 3000).errors).toEqual([
      'SINV-1 is allocated more than its outstanding amount',
      'The allocations come to more than the payment',
    ])
  })
})

describe('referenceRows', () => {
  it('is only the invoices with something allocated, in the shape the form fills', () => {
    const rows = referenceRows([OLD, NEW], { [key(OLD)]: 3000, [key(NEW)]: 0 })
    expect(rows).toEqual([
      expect.objectContaining({
        reference_doctype: 'Sales Invoice',
        reference_name: 'SINV-1',
        total_amount: 3000,
        outstanding_amount: 3000,
        allocated_amount: 3000,
        exchange_rate: 1,
      }),
    ])
  })
})
