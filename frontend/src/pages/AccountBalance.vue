<template>
  <AppPageHeader>
    <div class="flex min-w-0 items-center gap-3">
      <span class="text-lg font-semibold text-ink-gray-8">Account Balance</span>
    </div>
    <template #actions>
      <Button
        variant="ghost"
        icon-left="lucide-refresh-cw"
        label="Refresh"
        :loading="statementLoading"
        @click="reloadStatement()"
      />
    </template>
  </AppPageHeader>

  <div class="px-5 py-4">
    <div class="mx-auto max-w-3xl">
      <!-- Refused rather than arrived: say so, instead of leaving a skeleton up
           for a reply that is never coming. The same order the request pages
           open with, and for the same reason -- see `RequestGate`, which this
           page cannot use because it gates on a permission answer and there is
           no permission to answer here. -->
      <template v-if="statementError">
        <ErrorMessage :message="statementError.message" class="mb-3" />
        <Button label="Try again" variant="subtle" @click="reloadStatement()" />
      </template>

      <div v-else-if="!statementLoaded" class="space-y-3">
        <Skeleton class="h-24 w-full rounded-4" />
        <Skeleton class="h-64 w-full rounded-4" />
      </div>

      <!-- Three empty states, because they send the reader to three different
           people. No ledger on the site is a fact about the site; no account in
           your name is something whoever keeps the books can create; nothing on
           an account you do have is the happy answer and needs nobody. One
           message covering all three would send two thirds of its readers to
           the wrong place. -->
      <div v-else-if="!statement.ledger" class="mt-16 text-center">
        <span class="lucide-wallet mx-auto size-8 text-ink-gray-4" />
        <p class="mt-2 text-base-medium text-ink-gray-7">No accounts are kept here</p>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          This site doesn't run the accounts module, so there are no balances to show.
        </p>
      </div>

      <div v-else-if="!isParty" class="mt-16 text-center">
        <span class="lucide-wallet mx-auto size-8 text-ink-gray-4" />
        <p class="mt-2 text-base-medium text-ink-gray-7">You don't have an account here</p>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          Balances are kept against a customer, student, supplier or employee record. Ask
          Accounts to link yours to this login.
        </p>
      </div>

      <div
        v-else-if="!hasBalances"
        class="rounded-4 border border-dashed border-outline-gray-2 px-4 py-10 text-center"
      >
        <p class="text-base-medium text-ink-gray-7">Nothing on your account</p>
        <p class="mt-1 text-p-sm text-ink-gray-5">
          Nothing has been charged to you and nothing is outstanding.
        </p>
      </div>

      <template v-else>
        <!-- One headline per currency. A reader with one company -- nearly all
             of them -- never learns that this is a list. -->
        <section class="space-y-3">
          <BalanceHeadline
            v-for="total in statement.totals"
            :key="total.currency ?? ''"
            :total="total"
            :lending="statement.lending"
            :account-type="accountTypeFor(total.currency)"
          />
        </section>

        <section v-for="account in statement.accounts" :key="accountKey(account)" class="mt-8">
          <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h2 class="text-base-medium text-ink-gray-8">{{ heading(account) }}</h2>
            <p class="text-p-sm text-ink-gray-5">{{ standing(account) }}</p>
          </div>
          <StatementLines :account="account" class="mt-3" />
        </section>

        <section v-if="statement.loans.length" class="mt-8">
          <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
            <h2 class="text-base-medium text-ink-gray-8">Loans</h2>
            <!-- Why they are on their own. Worth one sentence: a reader who has
                 both will otherwise wonder why the loan is not on the statement
                 above, and the answer is that it is a separate agreement with a
                 separate schedule rather than an omission. -->
            <p class="text-p-sm text-ink-gray-5">Kept separately from your account</p>
          </div>
          <LoanBalances :loans="statement.loans" class="mt-3" />
        </section>
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Button, ErrorMessage, Skeleton } from 'frappe-ui'
import { formatExact } from '@/data/format'
import {
  balanceAmount,
  balanceSense,
  hasBalances,
  isParty,
  reloadStatement,
  statement,
  statementError,
  statementLoaded,
  statementLoading,
  type StatementAccount,
} from '@/data/statement'
import AppPageHeader from '@/components/AppPageHeader.vue'
import BalanceHeadline from '@/components/BalanceHeadline.vue'
import LoanBalances from '@/components/LoanBalances.vue'
import StatementLines from '@/components/StatementLines.vue'

/** A list key. A party can have a ledger with more than one company, and the
 *  pair is what makes a statement one statement. */
function accountKey(account: StatementAccount): string {
  return `${account.party_type}:${account.party}:${account.company}`
}

/**
 * What a statement is called.
 *
 * The party's own name, which is what the reader recognises, with the company
 * beside it only where there is more than one to tell apart. A single-company
 * site would otherwise print its own name over every section of every page,
 * which says nothing to anybody who works there.
 */
function heading(account: StatementAccount): string {
  const companies = new Set(statement.value.accounts.map((row) => row.company))
  return companies.size > 1 ? `${account.party_name} · ${account.company}` : account.party_name
}

/** Where this account stands, as a sentence rather than as a signed number. */
function standing(account: StatementAccount): string {
  const sense = balanceSense(account.balance, account.account_type)
  if (!account.balance) return 'Settled'
  return `${sense.label} ${formatExact(balanceAmount(account.balance), account.currency)}`
}

/**
 * Which way round the headline figure for one currency reads.
 *
 * `Mixed` when the accounts behind it do not agree -- somebody who is both a
 * customer and an employee is owed by one book and owes the other, and their
 * sum is a number with no sentence attached to it. The headline says so and
 * the sections below say it properly, which is better than a headline that
 * picks one of the two readings and is wrong for half of what it covers.
 */
function accountTypeFor(currency: string | null): 'Receivable' | 'Payable' | 'Mixed' {
  const kinds = new Set(
    statement.value.accounts
      .filter((account) => account.currency === currency)
      .map((account) => account.account_type),
  )
  return kinds.size === 1 ? [...kinds][0] : 'Mixed'
}
</script>
