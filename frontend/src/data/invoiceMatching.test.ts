import { describe, expect, it } from 'vitest'
import {
  checkInvoiceSplit,
  invoiceNumberAppears,
  suggestInvoices,
  type InvoiceRow,
  type PaymentHistory,
} from './invoiceMatching'
import type { TransactionRow } from './reconciliationRules'

function line(description: string, amount = 40000, values: Partial<TransactionRow> = {}): TransactionRow {
  return {
    name: 'BT-1',
    date: '2026-11-04',
    deposit: amount,
    withdrawal: 0,
    currency: 'NPR',
    description,
    reference_number: null,
    party_type: null,
    party: null,
    allocated_amount: 0,
    unallocated_amount: amount,
    status: 'Unreconciled',
    bank_account: 'OI Checking',
    company: 'OI',
    transaction_type: null,
    ...values,
  }
}

function invoice(name: string, customer: string, outstanding: number, due = '2026-10-01'): InvoiceRow {
  return {
    name,
    customer,
    customer_name: customer,
    company: 'OI',
    posting_date: due,
    due_date: due,
    grand_total: outstanding,
    outstanding_amount: outstanding,
    currency: 'NPR',
  }
}

const NIMA = invoice('SINV-Nepal 2083/84-00013', 'Nima Thing', 40000)
const PALLAVI = invoice('SINV-Nepal 2083/84-00012', 'Pallavi R. Shrestha', 40000)

describe('invoiceNumberAppears', () => {
  it('finds the whole name or the number after the series', () => {
    expect(invoiceNumberAppears(NIMA.name, 'fees SINV-Nepal 2083/84-00013')).toBe(true)
    expect(invoiceNumberAppears(NIMA.name, 'bill 2083/84-00013 nima')).toBe(true)
  })

  it('does not take the bare counter', () => {
    expect(invoiceNumberAppears(NIMA.name, 'ref 00013')).toBe(false)
    expect(invoiceNumberAppears('SINV-00013', 'ref 00013')).toBe(false)
  })
})

describe('suggestInvoices', () => {
  it('names nobody without evidence, however well the amount fits', () => {
    expect(suggestInvoices(line('FPQR-509212514-6001-24'), [NIMA, PALLAVI], [])).toEqual([])
  })

  it('finds the customer named in the description, strongly', () => {
    const [best, ...rest] = suggestInvoices(line('Transfer from NIMA THING'), [NIMA, PALLAVI], [])
    expect(best.invoice).toBe(NIMA.name)
    expect(best.strong).toBe(true)
    expect(best.reasons).toContain('Pays the invoice off exactly')
    expect(rest).toEqual([])
  })

  it('finds the customer by the party on the line', () => {
    const [best] = suggestInvoices(
      line('QR', 40000, { party_type: 'Customer', party: 'Pallavi R. Shrestha' }),
      [NIMA, PALLAVI],
      [],
    )
    expect(best.invoice).toBe(PALLAVI.name)
    expect(best.strong).toBe(true)
  })

  it('learns an account number from earlier payments, strongly only once it has repeated', () => {
    const once: PaymentHistory[] = [{ customer: 'Nima Thing', amount: 1000, description: 'from 9841234567' }]
    const [weak] = suggestInvoices(line('from 9841234567'), [NIMA, PALLAVI], once)
    expect(weak.invoice).toBe(NIMA.name)
    expect(weak.strong).toBe(false)

    const twice = [...once, { ...once[0] }]
    const [strong] = suggestInvoices(line('from 9841234567'), [NIMA, PALLAVI], twice)
    expect(strong.strong).toBe(true)
  })

  it('ignores an identifier seen with two customers', () => {
    const shared: PaymentHistory[] = [
      { customer: 'Nima Thing', amount: 1, description: 'via 1234567890' },
      { customer: 'Pallavi R. Shrestha', amount: 1, description: 'via 1234567890' },
    ]
    expect(suggestInvoices(line('via 1234567890'), [NIMA, PALLAVI], shared)).toEqual([])
  })

  it("puts a customer's oldest open invoice first", () => {
    const older = invoice('SINV-Nepal 2082/83-00002', 'Nima Thing', 40000, '2025-08-01')
    const [best] = suggestInvoices(line('Nima Thing'), [NIMA, older], [])
    expect(best.invoice).toBe(older.name)
  })

  it('takes the invoice number as strong evidence', () => {
    const [best] = suggestInvoices(line('fee 2083/84-00012'), [NIMA, PALLAVI], [])
    expect(best.invoice).toBe(PALLAVI.name)
    expect(best.strong).toBe(true)
  })

  it('suggests nothing for a withdrawal', () => {
    expect(suggestInvoices(line('Nima Thing', 0, { withdrawal: 40000, deposit: 0 }), [NIMA], [])).toEqual([])
  })
})

describe('checkInvoiceSplit', () => {
  const owed = { [NIMA.name]: 40000, [PALLAVI.name]: 40000 }

  it('accepts a split within the deposit and the invoices', () => {
    expect(
      checkInvoiceSplit(
        [
          { invoice: NIMA.name, amount: 25000 },
          { invoice: PALLAVI.name, amount: 15000 },
        ],
        40000,
        owed,
      ),
    ).toEqual({ total: 40000, remaining: 0, errors: [] })
  })

  it('refuses paying an invoice more than it owes, and more than the deposit', () => {
    const { errors } = checkInvoiceSplit([{ invoice: NIMA.name, amount: 50000 }], 40000, owed)
    expect(errors).toEqual([
      `${NIMA.name} is paid more than its outstanding amount`,
      'The lines come to more than the deposit',
    ])
  })
})
