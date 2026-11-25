/**
 * Which Sales Invoices a deposit probably pays, and whether a split of it can
 * be booked. The invoice tab's judgement, as `reconciliationRules.ts` is the
 * loan tab's: pure, so it can be tested, and fetched for by `reconciliation.ts`
 * (`useInvoiceBook`).
 *
 * The evidence is the loan tab's, read against customers instead of loans,
 * and weighed by the same Bank Reconciliation Settings (`LoanMatchingRules`).
 * A site tunes one set of weights for what its bank writes in a description,
 * whoever the payment turns out to be from.
 *
 * 1. the party on the line is the invoice's customer (strong);
 * 2. an identifier on this line was on two or more earlier payments of exactly
 *    one customer (strong), or on one (weak);
 * 3. the customer's whole name is in the description (strong);
 * 4. the invoice's number is in the description (strong);
 * 5. tie-breakers: the deposit pays the invoice off exactly, or is an amount
 *    this customer has paid before; and of one customer's invoices, the one
 *    due first.
 *
 * The weights of 1 to 3 are the settings' party, identifier and name weights;
 * 4 uses the name weight too, being the same kind of evidence: the payer wrote
 * down which bill it is.
 */

import {
  identifiers,
  loanMatchingRules,
  money,
  nameAppears,
  type LoanMatchingRules,
  type TransactionRow,
} from './reconciliationRules'

/** A submitted Sales Invoice with something left to pay. */
export interface InvoiceRow {
  name: string
  customer: string
  customer_name: string | null
  company: string
  posting_date: string
  due_date: string | null
  grand_total: number
  outstanding_amount: number
  currency: string
}

/** An earlier payment from a customer, with the description of the statement
 *  line it was matched to, where it was matched to one. */
export interface PaymentHistory {
  customer: string
  amount: number
  description: string | null
}

/** A payment already on the books and not yet on a statement line. */
export interface UnclearedPayment {
  name: string
  party: string
  party_name: string | null
  paid_amount: number
  posting_date: string
  reference_no: string | null
}

export interface InvoiceSuggestion {
  invoice: string
  score: number
  /** Whether it rests on evidence good enough to fill in the draft. */
  strong: boolean
  reasons: string[]
}

export interface InvoiceLine {
  invoice: string
  amount: number
}

/** Lower case, letters and digits, single spaces, padded: `SINV-Nepal 2083/84-00013`
 *  becomes ` sinv nepal 2083 84 00013 `. */
function normalise(text: string | null | undefined): string {
  return ` ${(text ?? '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim()} `
}

/**
 * Whether an invoice's number is in a description: the whole name, or the
 * part after its series (`2083/84-00013`). Never the bare counter, `00013`,
 * which is in half the descriptions of the year.
 */
export function invoiceNumberAppears(invoice: string, description: string | null | undefined): boolean {
  const text = normalise(description)
  if (text.trim() === '') return false
  const whole = normalise(invoice)
  if (text.includes(whole)) return true
  const tail = invoice.split(' ').pop() ?? ''
  const number = normalise(tail)
  return tail !== invoice && number.trim().split(' ').length > 1 && text.includes(number)
}

/**
 * The invoices a deposit probably pays, best first, with the reasons.
 *
 * Only invoices some evidence points at. Every open invoice is still offered
 * through the search beside the suggestions.
 */
export function suggestInvoices(
  transaction: TransactionRow,
  invoices: InvoiceRow[],
  history: PaymentHistory[],
  rules?: Partial<LoanMatchingRules> | null,
): InvoiceSuggestion[] {
  const weights = loanMatchingRules(rules)
  const amount = money(transaction.unallocated_amount)
  if (amount <= 0 || transaction.deposit <= 0) return []
  const ids = (description: string | null) => identifiers(description, weights.min_identifier_digits)

  // Which customers each identifier has been seen with; one seen with two
  // customers identifies neither.
  const seenWith = new Map<string, Map<string, number>>()
  const usualAmounts = new Map<string, Set<number>>()
  for (const row of history) {
    if (!usualAmounts.has(row.customer)) usualAmounts.set(row.customer, new Set())
    usualAmounts.get(row.customer)!.add(money(row.amount))
    for (const id of ids(row.description)) {
      if (!seenWith.has(id)) seenWith.set(id, new Map())
      const customers = seenWith.get(id)!
      customers.set(row.customer, (customers.get(row.customer) ?? 0) + 1)
    }
  }
  const lineIds = ids(transaction.description)

  // What is said about a customer is said about each of their invoices, so
  // it is worked out once per customer.
  const aboutCustomer = new Map<string, { score: number; strong: boolean; reasons: string[] }>()
  function customerEvidence(invoice: InvoiceRow) {
    const known = aboutCustomer.get(invoice.customer)
    if (known) return known
    let score = 0
    let strong = false
    const reasons: string[] = []
    if (
      transaction.party_type === 'Customer' &&
      transaction.party === invoice.customer &&
      weights.party_match_score > 0
    ) {
      score += weights.party_match_score
      strong = true
      reasons.push('Customer is the party on this line')
    }
    const matched = lineIds.filter((id) => {
      const customers = seenWith.get(id)
      return customers?.size === 1 && customers.has(invoice.customer)
    })
    const times = matched.length ? Math.max(...matched.map((id) => seenWith.get(id)!.get(invoice.customer)!)) : 0
    const idWeight = times > 1 ? weights.repeated_identifier_score : weights.single_identifier_score
    if (times && idWeight > 0) {
      score += idWeight
      strong ||= times > 1
      reasons.push(`${matched[0]} was on ${times === 1 ? 'an earlier payment' : `${times} earlier payments`}`)
    }
    if (
      weights.name_in_description_score > 0 &&
      nameAppears(invoice.customer_name || invoice.customer, transaction.description, weights.min_name_length)
    ) {
      score += weights.name_in_description_score
      strong = true
      reasons.push('Customer named in the description')
    }
    const evidence = { score, strong, reasons }
    aboutCustomer.set(invoice.customer, evidence)
    return evidence
  }

  const suggestions: InvoiceSuggestion[] = []
  for (const invoice of invoices) {
    const outstanding = money(invoice.outstanding_amount)
    if (outstanding <= 0) continue
    const about = customerEvidence(invoice)
    let score = about.score
    let strong = about.strong
    const reasons = [...about.reasons]

    if (weights.name_in_description_score > 0 && invoiceNumberAppears(invoice.name, transaction.description)) {
      score += weights.name_in_description_score
      strong = true
      reasons.push('Invoice number in the description')
    }

    let tieBreak = 0
    if (outstanding === amount) {
      if (weights.exact_payoff_score > 0) {
        tieBreak += weights.exact_payoff_score
        reasons.push('Pays the invoice off exactly')
      }
    } else if (weights.usual_amount_score > 0 && usualAmounts.get(invoice.customer)?.has(amount)) {
      tieBreak += weights.usual_amount_score
      reasons.push('Same amount as earlier payments')
    }

    if (score > 0) suggestions.push({ invoice: invoice.name, score: score + tieBreak, strong, reasons })
  }

  // One customer's evidence finds all their open invoices. The one due first
  // is what a payment usually settles.
  const byName = new Map(invoices.map((invoice) => [invoice.name, invoice]))
  const byCustomer = new Map<string, InvoiceSuggestion[]>()
  for (const suggestion of suggestions) {
    const customer = byName.get(suggestion.invoice)!.customer
    if (!byCustomer.has(customer)) byCustomer.set(customer, [])
    byCustomer.get(customer)!.push(suggestion)
  }
  const due = (name: string) => byName.get(name)!.due_date || byName.get(name)!.posting_date
  for (const group of byCustomer.values()) {
    if (group.length < 2) continue
    const first = group.reduce((best, row) => (due(row.invoice) < due(best.invoice) ? row : best))
    first.score += 1
    first.reasons.push("This customer's oldest open invoice")
  }
  return suggestions.sort((a, b) => b.score - a.score || a.invoice.localeCompare(b.invoice))
}

export interface InvoiceSplitCheck {
  total: number
  remaining: number
  errors: string[]
}

/**
 * Whether a split of a deposit across invoices can be booked. The server
 * refuses the same things (`invoice_payments._validated_lines`); they are
 * checked here so the button can say so first. Unlike a loan, an invoice
 * cannot be paid more than it owes from here: the excess would be an advance,
 * which the Payment entry tab books.
 */
export function checkInvoiceSplit(
  lines: InvoiceLine[],
  unallocated: number,
  outstanding: Record<string, number>,
): InvoiceSplitCheck {
  const errors: string[] = []
  const total = money(lines.reduce((sum, line) => sum + (line.amount || 0), 0))
  const remaining = money(unallocated - total)
  if (!lines.length) errors.push('Choose an invoice')
  const seen = new Set<string>()
  for (const line of lines) {
    if (seen.has(line.invoice)) errors.push(`${line.invoice} is on two lines`)
    seen.add(line.invoice)
    if (!(line.amount > 0)) errors.push(`${line.invoice} has no amount`)
    const owed = outstanding[line.invoice]
    if (owed !== undefined && money(line.amount) > money(owed)) {
      errors.push(`${line.invoice} is paid more than its outstanding amount`)
    }
  }
  if (remaining < 0) errors.push('The lines come to more than the deposit')
  return { total, remaining, errors }
}
