import { describe, expect, it } from 'vitest'
import {
  accountMatches,
  balanceBreaks,
  proposeRows,
  sameDescription,
  transactionFor,
  type ExistingLine,
  type StatementRow,
} from './statementImport'

/**
 * What the import dialog proposes. Getting "already imported" wrong in one
 * direction books a deposit twice; in the other it silently drops one.
 */

function row(date: string, deposit: number, withdrawal = 0, description = '', balance: number | null = null): StatementRow {
  const [year, month, day] = date.split('-').map(Number)
  return {
    date: { printed: date, year, month, day, calendar: 'AD' },
    description,
    reference: null,
    withdrawal,
    deposit,
    balance,
  }
}

function line(name: string, date: string, deposit: number, withdrawal = 0, description = ''): ExistingLine {
  return { name, date, deposit, withdrawal, description, reference_number: null }
}

describe('proposeRows', () => {
  it('marks a row with a line of the same date and amount as already imported', () => {
    const [found] = proposeRows({ rows: [row('2026-07-10', 5000)], opening_balance: null }, [
      line('BT-1', '2026-07-10', 5000),
    ])
    expect(found).toMatchObject({ status: 'duplicate', existing: 'BT-1', iso: '2026-07-10' })
  })

  it('does not match money going the other way', () => {
    const [found] = proposeRows({ rows: [row('2026-07-10', 0, 5000)], opening_balance: null }, [
      line('BT-1', '2026-07-10', 5000),
    ])
    expect(found.status).toBe('new')
  })

  it('pairs lines off one each, so a second identical deposit is new', () => {
    const rows = proposeRows(
      { rows: [row('2026-07-10', 5000), row('2026-07-10', 5000)], opening_balance: null },
      [line('BT-1', '2026-07-10', 5000)],
    )
    expect(rows.map((r) => r.status)).toEqual(['duplicate', 'new'])
  })

  it('gives each line to the row that describes it', () => {
    const rows = proposeRows(
      {
        rows: [row('2026-07-10', 5000, 0, 'FPQR-111'), row('2026-07-10', 5000, 0, 'FPQR-222')],
        opening_balance: null,
      },
      [line('BT-2', '2026-07-10', 5000, 0, 'FPQR-222')],
    )
    expect(rows.map((r) => [r.status, r.existing])).toEqual([
      ['new', null],
      ['duplicate', 'BT-2'],
    ])
  })

  it('accepts a line a day or two away only when the description agrees', () => {
    const existing = [line('BT-1', '2026-07-11', 5000, 0, 'CIPS/Heema Rai')]
    expect(proposeRows({ rows: [row('2026-07-10', 5000, 0, 'CIPS/Heema Rai')], opening_balance: null }, existing)[0].status).toBe(
      'duplicate',
    )
    expect(proposeRows({ rows: [row('2026-07-10', 5000, 0, 'Someone else')], opening_balance: null }, existing)[0].status).toBe(
      'new',
    )
  })

  it('refuses a date that is not a real day', () => {
    const [found] = proposeRows({ rows: [row('2026-02-30', 5000)], opening_balance: null }, [])
    expect(found).toMatchObject({ status: 'bad-date', iso: null })
  })

  it('converts a Bikram Sambat date', () => {
    const bs: StatementRow = { ...row('2026-07-10', 5000), date: { printed: '2083/03/26', year: 2083, month: 3, day: 26, calendar: 'BS' } }
    expect(proposeRows({ rows: [bs], opening_balance: null }, [])[0].iso).toBe('2026-07-10')
  })
})

describe('balanceBreaks', () => {
  it('finds the row whose balance does not follow', () => {
    const rows = [row('2026-07-01', 5000, 0, '', 105_000), row('2026-07-02', 0, 2000, '', 103_000), row('2026-07-03', 1000, 0, '', 105_000)]
    const found = balanceBreaks(rows, 100_000)
    expect([...found.broken]).toEqual([2])
    expect(found).toMatchObject({ checked: 3, newestFirst: false })
  })

  it('walks a statement printed newest first the other way', () => {
    const rows = [row('2026-07-02', 0, 2000, '', 103_000), row('2026-07-01', 5000, 0, '', 105_000)]
    const found = balanceBreaks(rows, null)
    expect(found).toMatchObject({ newestFirst: true, checked: 1 })
    expect(found.broken.size).toBe(0)
  })

  it('carries on across rows with no balance printed', () => {
    const rows = [row('2026-07-01', 5000, 0, '', null), row('2026-07-02', 1000, 0, '', 106_000)]
    expect(balanceBreaks(rows, 100_000).broken.size).toBe(0)
  })
})

describe('sameDescription', () => {
  it('sees a shared account or reference number', () => {
    expect(
      sameDescription({ description: 'FT/09711000594/Kiran', reference: null }, line('BT', '2026-07-10', 1, 0, 'mobile 09711000594')),
    ).toBe(true)
  })
})

describe('accountMatches', () => {
  it('compares digits, and allows a masked number', () => {
    expect(accountMatches('0011-1222-333', ['00111222333'])).toBe(true)
    expect(accountMatches('XXXXXX2333', ['00111222333'])).toBe(true)
    expect(accountMatches('99999', ['00111222333'])).toBe(false)
    expect(accountMatches(null, ['00111222333'])).toBeNull()
  })
})

describe('transactionFor', () => {
  it('is a submitted Bank Transaction on the account', () => {
    const [proposed] = proposeRows({ rows: [row('2026-07-10', 5000, 0, 'FPQR')], opening_balance: null }, [])
    expect(transactionFor(proposed, 'OI Checking - Laxmi Bank', 'NPR')).toEqual({
      doctype: 'Bank Transaction',
      docstatus: 1,
      date: '2026-07-10',
      bank_account: 'OI Checking - Laxmi Bank',
      deposit: 5000,
      withdrawal: 0,
      description: 'FPQR',
      reference_number: undefined,
      currency: 'NPR',
    })
  })
})
