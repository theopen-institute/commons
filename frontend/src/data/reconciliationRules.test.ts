import { describe, expect, it } from 'vitest'
import {
  checkSplit,
  identifiers,
  meaningfulReference,
  mergeCandidates,
  nameAppears,
  outstandingPrincipal,
  proposeAmount,
  proposedReference,
  repaymentCandidates,
  suggestLoans,
  type Candidate,
  type LoanRow,
  type RepaymentHistory,
  type TransactionRow,
} from './reconciliationRules'

/**
 * What the reconciliation page has to judge correctly. A wrong suggestion
 * looks exactly like a right one, and a bookkeeper working down forty lines
 * accepts what it offers.
 *
 * The descriptions are shaped like the real ones on register.localhost's
 * statements: named transfers, and QR payments that name nobody.
 */

function transaction(overrides: Partial<TransactionRow> = {}): TransactionRow {
  return {
    name: 'ACC-BTN-1',
    date: '2026-07-10',
    deposit: 5000,
    withdrawal: 0,
    currency: 'NPR',
    description: '',
    reference_number: '-',
    party_type: null,
    party: null,
    allocated_amount: 0,
    unallocated_amount: 5000,
    status: 'Unreconciled',
    bank_account: 'OI Checking - Laxmi Bank',
    company: 'Open Institute (Nepal)',
    transaction_type: null,
    ...overrides,
  }
}

function loan(name: string, applicant: string, overrides: Partial<LoanRow> = {}): LoanRow {
  return {
    name,
    applicant_type: 'Student',
    applicant,
    company: 'Open Institute (Nepal)',
    loan_product: 'Good Faith Loan',
    status: 'Disbursed',
    loan_amount: 50000,
    disbursed_amount: 50000,
    total_payment: 50000,
    total_principal_paid: 20000,
    total_interest_payable: 0,
    debit_adjustment_amount: 0,
    credit_adjustment_amount: 0,
    ...overrides,
  }
}

const KIRAN = loan('LOAN-KIRAN', 'kiran@example.org')
const HEEMA = loan('LOAN-HEEMA', 'heema@example.org')
const NAMES = { 'kiran@example.org': 'Kiran Adhikari', 'heema@example.org': 'Heema Rai' }

describe('outstandingPrincipal', () => {
  it('is the repayable total less what has been paid, on a disbursed loan', () => {
    expect(outstandingPrincipal(KIRAN)).toBe(30000)
  })

  it('leaves interest out, because it is principal', () => {
    expect(
      outstandingPrincipal(loan('L', 'a', { total_payment: 55000, total_interest_payable: 5000 })),
    ).toBe(30000)
  })

  it('counts only what has gone out on a loan still being disbursed', () => {
    expect(
      outstandingPrincipal(loan('L', 'a', { status: 'Partially Disbursed', disbursed_amount: 25000 })),
    ).toBe(5000)
  })

  it('applies adjustments', () => {
    expect(
      outstandingPrincipal(loan('L', 'a', { debit_adjustment_amount: 500, credit_adjustment_amount: 200 })),
    ).toBe(30300)
  })

  it('is never negative, even on an overpaid loan', () => {
    expect(outstandingPrincipal(loan('L', 'a', { total_principal_paid: 60000 }))).toBe(0)
  })
})

describe('identifiers', () => {
  it('finds account and phone numbers', () => {
    expect(
      identifiers('FT/09711000594/Kiran Adhikari/9814347967/000200325933/mobile payment,212356615'),
    ).toEqual(['09711000594', '9814347967', '000200325933', '212356615'])
  })

  it('ignores short numbers', () => {
    expect(identifiers('CIPS/OI ARR6/ref 2026')).toEqual([])
  })
})

describe('nameAppears', () => {
  it('matches a full name whatever the punctuation around it', () => {
    expect(nameAppears('Heema Rai', 'CIPS/ACCOUNTFT:Heema Rai/Heema Rai GFL/Open Institute')).toBe(true)
  })

  it('wants every part of the name, not only the surname', () => {
    expect(nameAppears('Heema Rai', 'transfer from Sita Rai')).toBe(false)
  })

  it('does not match part of a longer word', () => {
    expect(nameAppears('Asha Rai', 'Ashanti Raina')).toBe(false)
  })

  it('refuses a single short name, which would match anywhere', () => {
    expect(nameAppears('Rai', 'Rai')).toBe(false)
  })
})

describe('suggestLoans', () => {
  it('suggests the borrower named in the description', () => {
    const found = suggestLoans(
      transaction({ description: 'CIPS/ACCOUNTFT:Heema Rai/Heema Rai GFL/Open Institute' }),
      [KIRAN, HEEMA],
      NAMES,
      [],
    )
    expect(found.map((row) => row.loan)).toEqual(['LOAN-HEEMA'])
    expect(found[0].reasons).toContain('Borrower named in the description')
  })

  it('learns an account number from earlier repayments', () => {
    const history: RepaymentHistory[] = [
      { loan: 'LOAN-KIRAN', amount: 10000, description: 'FT/09711000594/9814347967/mobile' },
      { loan: 'LOAN-KIRAN', amount: 10000, description: 'FT/09711000594/9814347967/mobile' },
    ]
    const found = suggestLoans(
      transaction({ description: 'FT/09711000594/some sender/mobile payment' }),
      [KIRAN, HEEMA],
      NAMES,
      history,
    )
    expect(found.map((row) => row.loan)).toEqual(['LOAN-KIRAN'])
    expect(found[0].reasons[0]).toBe('09711000594 was on 2 earlier repayments')
  })

  it('counts a number seen only once as weak evidence', () => {
    const history: RepaymentHistory[] = [
      { loan: 'LOAN-KIRAN', amount: 10000, description: 'FON:IBFT:451883554:3387' },
    ]
    const [found] = suggestLoans(
      transaction({ description: 'FON:IBFT:451883554:3528' }),
      [KIRAN, HEEMA],
      NAMES,
      history,
    )
    expect(found.loan).toBe('LOAN-KIRAN')
    expect(found.strong).toBe(false)
    expect(found.reasons[0]).toBe('451883554 was on an earlier repayment')
  })

  it('counts a name, or a number seen twice, as strong', () => {
    const history: RepaymentHistory[] = [
      { loan: 'LOAN-KIRAN', amount: 1, description: 'FT/09711000594' },
      { loan: 'LOAN-KIRAN', amount: 1, description: 'FT/09711000594' },
    ]
    expect(suggestLoans(transaction({ description: 'FT/09711000594' }), [KIRAN], NAMES, history)[0].strong).toBe(true)
    expect(suggestLoans(transaction({ description: 'Heema Rai' }), [HEEMA], NAMES, [])[0].strong).toBe(true)
  })

  it('prefers the loan a borrower with two paid last', () => {
    const older = loan('LOAN-1', 'heema@example.org')
    const newer = loan('LOAN-2', 'heema@example.org')
    const found = suggestLoans(transaction({ description: 'Heema Rai' }), [older, newer], NAMES, [
      { loan: 'LOAN-1', amount: 5000, description: null },
      { loan: 'LOAN-2', amount: 5000, description: null },
    ])
    expect(found.map((row) => row.loan)).toEqual(['LOAN-2', 'LOAN-1'])
    expect(found[0].reasons).toContain('The loan this borrower paid last')
  })

  it('does not trust a number seen with two different loans', () => {
    // A branch or clearing code, on everybody's lines.
    const history: RepaymentHistory[] = [
      { loan: 'LOAN-KIRAN', amount: 5000, description: 'CIPS/100000001/x' },
      { loan: 'LOAN-HEEMA', amount: 5000, description: 'CIPS/100000001/y' },
    ]
    expect(
      suggestLoans(transaction({ description: 'CIPS/100000001/z' }), [KIRAN, HEEMA], NAMES, history),
    ).toEqual([])
  })

  it('never suggests on the amount alone', () => {
    // Half the borrowers pay 5,000. A QR payment with no name is left to
    // the bookkeeper rather than guessed at.
    const history: RepaymentHistory[] = [{ loan: 'LOAN-KIRAN', amount: 5000, description: null }]
    expect(
      suggestLoans(
        transaction({ description: 'FPQR-446377887-5650-24:FPQR/100230441842:26071/00004068' }),
        [loan('LOAN-KIRAN', 'kiran@example.org', { total_principal_paid: 45000 })],
        NAMES,
        history,
      ),
    ).toEqual([])
  })

  it('puts the party on the line first', () => {
    const found = suggestLoans(
      transaction({
        party_type: 'Student',
        party: 'kiran@example.org',
        description: 'CIPS/ACCOUNTFT:Heema Rai/Heema Rai GFL',
      }),
      [KIRAN, HEEMA],
      NAMES,
      [],
    )
    expect(found.map((row) => row.loan)).toEqual(['LOAN-KIRAN', 'LOAN-HEEMA'])
  })

  it('breaks a tie with the amount that pays the loan off', () => {
    const payingOff = loan('LOAN-A', 'a', { total_principal_paid: 45000 })
    const other = loan('LOAN-B', 'b')
    const found = suggestLoans(
      transaction({ description: 'from Asmita Gurung' }),
      [other, payingOff],
      { a: 'Asmita Gurung', b: 'Asmita Gurung' },
      [],
    )
    expect(found.map((row) => row.loan)).toEqual(['LOAN-A', 'LOAN-B'])
    expect(found[0].reasons).toContain('Pays the loan off exactly')
  })

  it('leaves out loans with nothing left to repay', () => {
    const paid = loan('LOAN-HEEMA', 'heema@example.org', { total_principal_paid: 50000 })
    expect(
      suggestLoans(transaction({ description: 'Heema Rai' }), [paid], NAMES, []),
    ).toEqual([])
  })

  it('suggests nothing for a withdrawal', () => {
    expect(
      suggestLoans(
        transaction({ deposit: 0, withdrawal: 5000, description: 'Heema Rai' }),
        [HEEMA],
        NAMES,
        [],
      ),
    ).toEqual([])
  })
})

describe('references', () => {
  it('treats the bank’s dash as no reference', () => {
    expect(meaningfulReference('-')).toBe('')
    expect(meaningfulReference(' 0 ')).toBe('')
    expect(meaningfulReference('CHQ 004512')).toBe('CHQ 004512')
  })

  it('falls back to the description, trimmed to what the field holds', () => {
    const long = 'x'.repeat(200)
    expect(proposedReference(transaction({ description: long }))).toHaveLength(140)
    expect(proposedReference(transaction({ reference_number: 'R-1', description: long }))).toBe('R-1')
  })
})

describe('repaymentCandidates', () => {
  const repayment = {
    name: 'LM-REP-1',
    against_loan: 'LOAN-KIRAN',
    applicant_type: 'Student',
    applicant: 'kiran@example.org',
    amount_paid: 5000,
    value_date: '2026-07-10 00:00:00',
    reference_number: 'R-9',
    reference_date: '2026-07-10',
  }

  it('ranks as ERPNext does: one, plus reference, party and amount', () => {
    const [row] = repaymentCandidates(
      transaction({ reference_number: 'R-9', party_type: 'Student', party: 'kiran@example.org' }),
      [repayment],
      false,
    )
    expect(row.rank).toBe(4)
    expect(row.paid_amount).toBe(5000)
    expect(row.posting_date).toBe('2026-07-10')
  })

  it('does not count two blank references as a match', () => {
    const [row] = repaymentCandidates(
      transaction({ reference_number: '-' }),
      [{ ...repayment, reference_number: '-', amount_paid: 1 }],
      false,
    )
    expect(row.rank).toBe(1)
  })

  it('keeps only exact amounts when asked', () => {
    expect(
      repaymentCandidates(transaction(), [{ ...repayment, amount_paid: 4000 }], true),
    ).toEqual([])
  })
})

describe('mergeCandidates', () => {
  it('sorts by rank and keeps each source’s order within a rank', () => {
    const row = (name: string, rank: number): Candidate => ({
      rank,
      doctype: 'Payment Entry',
      name,
      paid_amount: 1,
      reference_no: null,
      reference_date: null,
      posting_date: null,
      party_type: null,
      party: null,
      currency: null,
    })
    expect(
      mergeCandidates([row('a', 2), row('b', 1)], [row('c', 3), row('d', 2)]).map((r) => r.name),
    ).toEqual(['c', 'a', 'd', 'b'])
  })
})

describe('checkSplit', () => {
  it('accepts a split that fits the deposit', () => {
    const check = checkSplit(
      [
        { loan: 'A', amount: 3000 },
        { loan: 'B', amount: 2000 },
      ],
      5000,
      { A: 10000, B: 10000 },
    )
    expect(check).toEqual({ total: 5000, remaining: 0, errors: [], warnings: [] })
  })

  it('does not trip on floating point', () => {
    expect(
      checkSplit(
        [
          { loan: 'A', amount: 0.1 },
          { loan: 'B', amount: 0.2 },
        ],
        0.3,
        {},
      ).errors,
    ).toEqual([])
  })

  it('refuses more than the deposit, a blank amount and a loan twice', () => {
    const check = checkSplit(
      [
        { loan: 'A', amount: 6000 },
        { loan: 'A', amount: 0 },
      ],
      5000,
      {},
    )
    expect(check.errors).toEqual([
      'A is on two lines',
      'A has no amount',
      'The lines come to more than the deposit',
    ])
  })

  it('warns, and only warns, about paying more than is owed', () => {
    const check = checkSplit([{ loan: 'A', amount: 5000 }], 5000, { A: 4000 })
    expect(check.errors).toEqual([])
    expect(check.warnings).toEqual(['A is paid 1000.00 more than its outstanding principal'])
  })
})

describe('proposeAmount', () => {
  it('takes what is left of the deposit, up to what the loan owes', () => {
    expect(proposeAmount(5000, 30000)).toBe(5000)
    expect(proposeAmount(5000, 3000)).toBe(3000)
    expect(proposeAmount(0, 3000)).toBe(0)
  })
})
