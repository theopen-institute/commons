import { describe, expect, it } from 'vitest'
import {
  checks,
  draftFrom,
  draftProblems,
  invoicePayload,
  isoDate,
  isTaxed,
  lineFlags,
  lineProblem,
  rateFromTotal,
  scanProblems,
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

  it('takes a line that prints no quantity as one of it', () => {
    const extracted = scanned({ lines: [{ description: 'Audit fee', quantity: null, rate: 5000, amount: 5000 }] })
    expect(draftFrom(reading({ extracted }), '2026-09-23').lines[0].qty).toBe(1)
  })

  it('takes the row total as the rate where no rate is printed, and says so', () => {
    const extracted = scanned({ lines: [{ description: 'Audit fee', quantity: null, rate: null, amount: 5000 }] })
    const [line] = draftFrom(reading({ extracted }), '2026-09-23').lines
    expect([line.qty, line.rate, line.amount]).toEqual([1, 5000, 5000])
    expect(rateFromTotal(line)).toBe(true)
    expect(lineFlags(line).message).toBeNull()
    line.rate = 4000
    expect(rateFromTotal(line)).toBe(false)
  })

  it('copies the total as the rate even beside a printed quantity, and then flags the line', () => {
    const extracted = scanned({ lines: [{ description: 'Router rental', quantity: 3, rate: null, amount: 4500 }] })
    const [line] = draftFrom(reading({ extracted }), '2026-09-23').lines
    expect(line.rate).toBe(4500)
    expect(lineProblem(line)).toContain('As read, 3 × 4500 is 13500')
  })

  it('leaves a rate empty where neither a rate nor a row total is printed', () => {
    const extracted = scanned({ lines: [{ description: 'Audit fee', quantity: 2, rate: null, amount: null }] })
    const [line] = draftFrom(reading({ extracted }), '2026-09-23').lines
    expect(line.rate).toBeNull()
    expect(line.amount).toBeNull()
  })
})

function flexLine() {
  const extracted = scanned({ lines: [{ description: 'Flex print', quantity: 3, rate: 1500, amount: 4800 }] })
  return draftFrom(reading({ extracted }), '2026-09-23').lines[0]
}

describe('lineFlags', () => {
  it('says nothing about a line that adds up', () => {
    const [line] = draftFrom(reading(), '2026-09-23').lines
    expect(lineFlags(line)).toEqual({ qty: false, rate: false, amount: false, message: null })
  })

  it('rings all three figures of a row that does not multiply out, since any could be the misread one', () => {
    const flags = lineFlags(flexLine())
    expect([flags.qty, flags.rate, flags.amount]).toEqual([true, true, true])
    expect(flags.message).toContain('As read')
    expect(flags.message).toContain('4500')
    expect(flags.message).toContain('4800')
  })

  it('rings a missing rate, which there is no booking without, and asks for it from the paper', () => {
    const extracted = scanned({ lines: [{ description: 'Audit fee', quantity: null, rate: null, amount: null }] })
    const flags = lineFlags(draftFrom(reading({ extracted }), '2026-09-23').lines[0])
    expect([flags.qty, flags.rate, flags.amount]).toEqual([false, true, false])
    expect(flags.message).toBe('No rate was read for this line. Enter it from the paper.')
  })

  it('does not fault a line that prints no row total; it only has nothing to check', () => {
    const extracted = scanned({ lines: [{ description: 'Audit fee', quantity: 2, rate: 2500, amount: null }] })
    expect(lineFlags(draftFrom(reading({ extracted }), '2026-09-23').lines[0]).message).toBeNull()
  })

  it('counts an assumed quantity of one as read', () => {
    const extracted = scanned({ lines: [{ description: 'Audit fee', quantity: null, rate: 5000, amount: 4000 }] })
    expect(lineProblem(draftFrom(reading({ extracted }), '2026-09-23').lines[0])).toContain('As read')
  })

  it('counts a cleared field as missing, not as zero', () => {
    const line = flexLine()
    ;(line as { rate: unknown }).rate = ''
    expect(lineFlags(line).rate).toBe(true)
  })

  it('follows the draft, so it clears once the reader corrects the row and returns if they break it', () => {
    const line = flexLine()
    line.rate = 1600
    expect(lineProblem(line)).toBeNull()
    line.qty = 2
    expect(lineProblem(line)).not.toContain('As read')
  })
})

describe('scanProblems', () => {
  it('has nothing to say about a bill whose figures agree', () => {
    expect(scanProblems(draftFrom(reading(), '2026-09-23'), scanned())).toEqual([])
  })

  it('catches a tax amount that is not its printed rate of the subtotal', () => {
    const extracted = scanned({ taxes: [{ label: 'VAT 13%', rate: 13, amount: 1500 }], total: 11500 })
    const found = scanProblems(draftFrom(reading({ extracted }), '2026-09-23'), extracted)
    expect(found).toEqual(['VAT 13% at 13% of 10000 is 1300, not the printed 1500.'])
  })

  it('catches a printed total the printed figures do not come to, and says when it is only rounding', () => {
    const misread = scanned({ total: 11800 })
    expect(scanProblems(draftFrom(reading({ extracted: misread }), '2026-09-23'), misread)[0]).toContain(
      'printed total is 11800.',
    )
    const rounded = scanned({ total: 11300.4 })
    expect(scanProblems(draftFrom(reading({ extracted: rounded }), '2026-09-23'), rounded)[0]).toContain(
      'may be rounding',
    )
  })

  it('accepts a subtotal printed before the discount or after it', () => {
    const before = scanned({ subtotal: 10000, discount: 500, taxes: [{ label: 'VAT', rate: 13, amount: 1235 }], total: 10735 })
    const after = scanned({ subtotal: 9500, discount: 500, taxes: [{ label: 'VAT', rate: 13, amount: 1235 }], total: 10735 })
    for (const extracted of [before, after]) {
      expect(scanProblems(draftFrom(reading({ extracted }), '2026-09-23'), extracted)).toEqual([])
    }
  })

  it('charges the tax on quantity × rate where no subtotal is printed, never on the row totals', () => {
    // The row total is misread as 12000; quantity × rate is 10000, and VAT of
    // 1300 is right for that.
    const extracted = scanned({
      subtotal: null,
      lines: [{ description: 'Internet', quantity: 1, rate: 10000, amount: 12000 }],
    })
    expect(scanProblems(draftFrom(reading({ extracted }), '2026-09-23'), extracted)).toEqual([])
  })

  it('does not check the printed total without a printed subtotal to check it with', () => {
    const extracted = scanned({ subtotal: null, total: 99999 })
    expect(scanProblems(draftFrom(reading({ extracted }), '2026-09-23'), extracted)).toEqual([])
  })

  it('stays silent where a figure it needs is not printed, rather than filling it in', () => {
    const extracted = scanned({
      subtotal: null,
      lines: [{ description: 'Internet', quantity: null, rate: null, amount: null }],
    })
    expect(scanProblems(draftFrom(reading({ extracted }), '2026-09-23'), extracted)).toEqual([])
  })

  it('says when a tax amount could not be read', () => {
    const extracted = scanned({ taxes: [{ label: 'VAT 13%', rate: 13, amount: null }] })
    expect(scanProblems(draftFrom(reading({ extracted }), '2026-09-23'), extracted)).toEqual([
      'No amount was read for VAT 13%.',
    ])
  })
})

describe('checks', () => {
  function stages(overrides: Partial<ScannedInvoice> = {}, sums: Partial<Totals> = {}) {
    const extracted = scanned(overrides)
    return checks(extracted, totals(sums))
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

  it('has nothing to compare the lines with where no subtotal is printed, and sums no row totals instead', () => {
    const lines = stages({ subtotal: null })[0]
    expect(lines.source).toBe('none printed')
    expect(lines.scan).toBeNull()
    expect(lines.matches).toBeNull()
  })

  it('catches lines whose quantity × rate does not come to the printed subtotal', () => {
    const lines = stages({ subtotal: 12000 })[0]
    expect(lines.matches).toBe(false)
  })

  it('shows no figure for a total the scan does not print', () => {
    const total = stages({ total: null }).find((check) => check.key === 'total')!
    expect(total.scan).toBeNull()
    expect(total.matches).toBeNull()
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
