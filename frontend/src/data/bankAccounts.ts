import { computed } from 'vue'
import { useSelfServiceRecords } from './selfService'

/**
 * The bank accounts payroll holds against this employee.
 *
 * Read-only, and that is a policy rather than an omission -- see
 * `BANK_ACCOUNT` in `tbs_commons.self_service.policies`. Payroll destination
 * details are the classic payment-diversion target, so a form that changes them
 * is a decision to be taken on purpose with its own verification, not one
 * inherited from the profile page because the machinery was already there.
 *
 * Several per employee, which is the second shape the registry supports: there
 * is no "my bank account" to resolve, so the page lists them. Ownership chains
 * through the employee record rather than through the login -- an account names
 * its `party`, and whoever owns that employee owns it.
 */

export const RECORD = 'Bank Account'

export interface BankAccount {
  name: string
  account_name: string | null
  bank: string | null
  account_type: string | null
  account_subtype: string | null
  bank_account_no: string | null
  iban: string | null
  branch_code: string | null
  is_default: 0 | 1
  disabled: 0 | 1
  is_company_account: 0 | 1
  party_type: string | null
  party: string | null
  modified: string
}

const source = useSelfServiceRecords<BankAccount>(RECORD)

export const bankCan = source.can
export const bankPermissionsLoaded = source.permissionsLoaded
export const bankPermissionsError = source.permissionsError
export const bankAccountsLoaded = source.recordsLoaded
export const bankAccountsError = source.recordsError
export const reloadBankAccounts = source.reload

/** Default account first, then disabled ones last — the order someone scanning
 *  the page for "where does my pay go" would want. */
export const bankAccounts = computed(() =>
  [...source.records.value].sort(
    (a, b) => b.is_default - a.is_default || a.disabled - b.disabled,
  ),
)
