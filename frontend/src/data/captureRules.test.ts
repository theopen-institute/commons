import { describe, expect, it } from 'vitest'
import {
  checks,
  draftFrom,
  draftProblems,
  invoicePayload,
  isoDate,
  isTaxed,
  lineFixes,
  lineProblem,
  rowsMatchSubtotal,
  totalMatches,
  type Reading,
  type ScannedInvoice,
  type Totals,
} from './captureRules'

/**
 * What the scan page has to get right before a person looks at the draft. A
 * wrong date or a quietly accepted total reads exactly like a right one.
 *
 * The invoices are shaped like the ones on register.localhost: Nepali VAT
 * bills, dated in Bikram Sambat, 13% on the net.
 */

function scanned(overrides: Partial<ScannedInvoice> = {}): ScannedInvoice {
  return {
    is_invoice: true,
    supplier: { name: 'Vianet Communications Pvt. Ltd.', tax_id: '301234567' },
    buyer: { name: 'Kula Culture Management Training Pvt. Ltd.', tax_id: null },
    invoice_number: 'INV-2081-554',
    invoice_date: { printed: '2081/05/12', year: 2081, month: 5, day: 12, calendar: 'BS' },
    due_date: null,
    currency: 'NPR',
    lines: [{ description: 'Internet 6 months', quantity: 1, rate: 10000, amount: 10000 }],
    discount: null,
    subtotal: 10000,
    taxes: [{ label: 'VAT 13%', rate: 13, amount: 1300 }],
    total: 11300,
    notes: [],
    ...overrides,
  }
}

function reading(overrides: Partial<Reading> = {}): Reading {
  return {
    extracted: scanned(),
    companies: [],
    company: { name: 'Kula Culture Management Training, Pvt. Ltd.', reason: 'Billed to' },
    suppliers: [
      {
        name: 'Vianet Communications Pvt.Ltd',
        supplier_name: 'Vianet Communications Pvt.Ltd',
        tax_id: null,
        reason: 'Same name',
        strong: true,
      },
    ],
    model: 'claude-opus-5',
    ...overrides,
  }
}

function totals(overrides: Partial<Totals> = {}): Totals {
  return {
    currency: 'NPR',
    total: 10000,
    net_total: 10000,
    discount_amount: 0,
    taxes: [{ description: 'VAT', amount: 1300 }],
    total_taxes_and_charges: 1300,
    grand_total: 11300,
    rounded_total: 11300,
    ...overrides,
  }
}

describe('isoDate', () => {
  it('converts a Bikram Sambat date with the picker’s own tables', () => {
    expect(isoDate({ printed: '2082/01/01', year: 2082, month: 1, day: 1, calendar: 'BS' })).toBe('2025-04-14')
    expect(isoDate({ printed: '२०८१/०५/१२', year: 2081, month: 5, day: 12, calendar: 'BS' })).toBe('2024-08-28')
  })

  it('passes a Gregorian date through', () => {
    expect(isoDate({ printed: '1 Sep 2026', year: 2026, month: 9, day: 1, calendar: 'AD' })).toBe('2026-09-01')
  })

  it('gives nothing for a date that does not exist rather than a neighbouring one', () => {
    expect(isoDate({ printed: '30/02/2026', year: 2026, month: 2, day: 30, calendar: 'AD' })).toBeNull()
    expect(isoDate({ printed: '2081/13/01', year: 2081, month: 13, day: 1, calendar: 'BS' })).toBeNull()
  })

  it('gives nothing for no date', () => {
    expect(isoDate(null)).toBeNull()
  })
})

describe('draftFrom', () => {
  it('dates the posting as the invoice is dated', () => {
    const draft = draftFrom(reading(), '2026-09-23')
    expect(draft.bill_date).toBe('2024-08-28')
    expect(draft.posting_date).toBe('2024-08-28')
  })

  it('falls back to today where the scan has no usable date', () => {
    const draft = draftFrom(reading({ extracted: scanned({ invoice_date: null }) }), '2026-09-23')
    expect(draft.bill_date).toBe('')
    expect(draft.posting_date).toBe('2026-09-23')
  })

  it('chooses a strong supplier and leaves a merely similar one to the reader', () => {
    expect(draftFrom(reading(), '2026-09-23').supplier).toBe('Vianet Communications Pvt.Ltd')
    const similar = reading({
      suppliers: [{ name: 'Vianet', supplier_name: 'Vianet', tax_id: null, reason: 'Similar', strong: false }],
    })
    expect(draftFrom(similar, '2026-09-23').supplier).toBe('')
  })

  it('keeps each line’s scanned figures to check against', () => {
    const [line] = draftFrom(reading(), '2026-09-23').lines
    expect(line.description).toBe('Internet 6 months')
    expect(line.rate).toBe(10000)
    expect(line.scanned?.amount).toBe(10000)
    expect(line.expense_account).toBe('')
  })

  it('treats a missing quantity as one', () => {
    const extracted = scanned({ lines: [{ description: 'Audit fee', quantity: 0, rate: 5000, amount: 5000 }] })
    expect(draftFrom(reading({ extracted }), '2026-09-23').lines[0].qty).toBe(1)
  })
})

function flexLine() {
  const extracted = scanned({ lines: [{ description: 'Flex print', quantity: 3, rate: 1500, amount: 4800 }] })
  return draftFrom(reading({ extracted }), '2026-09-23').lines[0]
}

describe('lineProblem', () => {
  it('says nothing about a line that adds up', () => {
    const [line] = draftFrom(reading(), '2026-09-23').lines
    expect(line.amount).toBe(10000)
    expect(lineProblem(line)).toBeNull()
  })

  it('points at a row whose total is not quantity times rate, and says it is as printed', () => {
    const problem = lineProblem(flexLine())
    expect(problem).toContain('As printed')
    expect(problem).toContain('4800')
    expect(problem).toContain('4500')
  })

  it('follows the draft, so it clears once the reader fixes the row and returns if they break it', () => {
    const line = flexLine()
    line.rate = 1600
    expect(lineProblem(line)).toBeNull()
    line.qty = 2
    expect(lineProblem(line)).not.toContain('As printed')
  })

  it('has nothing to say about a line with no row total', () => {
    const line = flexLine()
    line.amount = null
    expect(lineProblem(line)).toBeNull()
  })
})

describe('lineFixes', () => {
  it('offers the rate that makes the row total, or the total that the rate makes', () => {
    const line = flexLine()
    line.amount = 4800
    line.qty = 3
    line.rate = 1500
    expect(lineFixes(line).map((fix) => fix.values)).toEqual([{ rate: 1600 }, { amount: 4500 }])
  })

  it('books one of the total where no rate to the cent would make it', () => {
    const line = flexLine()
    line.amount = 100
    line.rate = 33
    expect(lineFixes(line)[0].values).toEqual({ qty: 1, rate: 100 })
  })

  it('offers nothing for a line that adds up', () => {
    expect(lineFixes(draftFrom(reading(), '2026-09-23').lines[0])).toEqual([])
  })
})

describe('rowsMatchSubtotal', () => {
  it('accepts a subtotal printed before the discount or after it', () => {
    const draft = draftFrom(reading(), '2026-09-23')
    expect(rowsMatchSubtotal(draft, scanned())).toBe(true)
    draft.discount_amount = 500
    expect(rowsMatchSubtotal(draft, scanned({ subtotal: 9500 }))).toBe(true)
  })

  it('catches a line that is missing', () => {
    const draft = draftFrom(reading(), '2026-09-23')
    expect(rowsMatchSubtotal(draft, scanned({ subtotal: 12000 }))).toBe(false)
  })

  it('has no opinion where no subtotal is printed', () => {
    expect(rowsMatchSubtotal(draftFrom(reading(), '2026-09-23'), scanned({ subtotal: null }))).toBeNull()
  })
})

describe('checks', () => {
  function stages(overrides: Partial<ScannedInvoice> = {}, sums: Partial<Totals> = {}) {
    const extracted = scanned(overrides)
    const draft = draftFrom(reading({ extracted }), '2026-09-23')
    return checks(draft, extracted, totals(sums))
  }

  it('agrees at every stage for a bill that adds up', () => {
    expect(stages().map((check) => [check.key, check.matches])).toEqual([
      ['lines', true],
      ['tax', true],
      ['total', true],
    ])
  })

  it('puts a wrong tax at the tax stage, not the lines', () => {
    const found = stages({}, { total_taxes_and_charges: 0, taxes: [], grand_total: 10000, rounded_total: 10000 })
    expect(found.find((check) => check.key === 'lines')?.matches).toBe(true)
    expect(found.find((check) => check.key === 'tax')?.matches).toBe(false)
  })

  it('compares the lines with the row totals where no subtotal is printed', () => {
    const lines = stages({ subtotal: null })[0]
    expect(lines.source).toBe('sum of the row totals')
    expect(lines.scan).toBe(10000)
  })

  it('leaves the tax out where neither the scan nor the draft has any', () => {
    const found = stages({ taxes: [], total: 10000 }, { total_taxes_and_charges: 0, taxes: [], grand_total: 10000, rounded_total: 10000 })
    expect(found.map((check) => check.key)).toEqual(['lines', 'total'])
  })
})

describe('totalMatches', () => {
  it('accepts either the grand or the rounded total', () => {
    expect(totalMatches(11300, totals())).toBe(true)
    expect(totalMatches(11300, totals({ grand_total: 11299.6, rounded_total: 11300 }))).toBe(true)
    expect(totalMatches(11299.6, totals({ grand_total: 11299.6, rounded_total: 11300 }))).toBe(true)
  })

  it('refuses a total that is off by a misread digit', () => {
    expect(totalMatches(11800, totals())).toBe(false)
  })

  it('has no opinion where the scan printed no total', () => {
    expect(totalMatches(null, totals())).toBeNull()
  })
})

describe('isTaxed', () => {
  it('is whether any tax has an amount', () => {
    expect(isTaxed(scanned())).toBe(true)
    expect(isTaxed(scanned({ taxes: [] }))).toBe(false)
    expect(isTaxed(scanned({ taxes: [{ label: 'VAT', rate: 13, amount: 0 }] }))).toBe(false)
  })
})

describe('the draft sent to the server', () => {
  it('asks for a supplier to be made rather than naming one', () => {
    const draft = draftFrom(reading(), '2026-09-23')
    draft.newSupplier = { supplier_name: 'New Traders', tax_id: '' }
    expect(invoicePayload(draft).supplier).toBeNull()
  })

  it('carries only what the server reads from a line', () => {
    const draft = draftFrom(reading(), '2026-09-23')
    draft.lines[0].expense_account = 'Utility Expenses - KC'
    expect(invoicePayload(draft).items).toEqual([
      { description: 'Internet 6 months', qty: 1, rate: 10000, expense_account: 'Utility Expenses - KC' },
    ])
  })

  it('is held back, beside the field, until every line has an account', () => {
    const draft = draftFrom(reading(), '2026-09-23')
    expect(draftProblems(draft)).toEqual({ 'account-0': 'Choose an account' })
    draft.lines[0].expense_account = 'Utility Expenses - KC'
    expect(draftProblems(draft)).toEqual({})
  })

  it('refuses a due date before the posting date', () => {
    const draft = draftFrom(reading(), '2026-09-23')
    draft.lines[0].expense_account = 'Utility Expenses - KC'
    draft.due_date = '2024-08-01'
    expect(draftProblems(draft).due_date).toBeDefined()
  })
})
