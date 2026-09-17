<template>
	<AppPageHeader>
		<span class="text-lg font-semibold text-ink-gray-8">Bank accounts</span>
		<template #actions>
			<Button
				variant="ghost"
				icon-left="lucide-refresh-cw"
				label="Refresh"
				:loading="!bankAccountsLoaded"
				@click="reloadBankAccounts()"
			/>
		</template>
	</AppPageHeader>

	<div class="px-5 py-4">
		<!-- The permission answer refused rather than arrived: say so, instead of
		     leaving a skeleton up for a reply that is never coming. -->
		<div v-if="loadError" class="mx-auto max-w-3xl">
			<ErrorMessage :message="loadError.message" class="mb-3" />
			<Button label="Try again" variant="subtle" @click="reloadBankAccounts()" />
		</div>

		<div v-else-if="!bankAccountsLoaded" class="mx-auto max-w-3xl space-y-3">
			<Skeleton v-for="n in 2" :key="n" class="h-24 w-full rounded-4" />
		</div>

		<!-- Three endings, and which one it is decides who to ask. Withheld
		     records are a permissions question; none at all is payroll's. -->
		<div v-else-if="!bankAccounts.length" class="mx-auto mt-16 max-w-md text-center">
			<span
				class="mx-auto size-8 text-ink-gray-4"
				:class="bankCan.record_access === 'forbidden' ? 'lucide-lock' : 'lucide-landmark'"
			/>
			<template v-if="bankCan.record_access === 'forbidden'">
				<p class="mt-2 text-base-medium text-ink-gray-7">
					You don't have access to these records
				</p>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					Your account isn't permitted to open bank accounts, so there is nothing to show
					here either way. If you should be able to see yours, ask a System Manager to
					review the permissions.
				</p>
			</template>
			<template v-else>
				<p class="mt-2 text-base-medium text-ink-gray-7">
					No bank accounts are registered for your employee ID
				</p>
				<p class="mt-1 text-p-sm text-ink-gray-5">
					If you need to add a new account, contact a System Manager
				</p>
			</template>
		</div>

		<div v-else class="mx-auto max-w-3xl">
			<Alert
				theme="gray"
				title="This page is read only"
				description="Bank details are held by payroll. To change where you're paid, talk to them directly — this isn't something to send through a form."
			/>

			<ul class="mt-6 space-y-3">
				<li
					v-for="account in bankAccounts"
					:key="account.name"
					class="rounded-4 border border-outline-gray-1 p-4"
					:class="account.disabled ? 'opacity-60' : ''"
				>
					<div class="flex flex-wrap items-start justify-between gap-2">
						<h2 class="text-lg font-semibold text-ink-gray-8">
							{{ account.account_name || account.name }}
						</h2>
						<div class="flex shrink-0 items-center gap-2">
							<Badge v-if="account.is_default" theme="green" variant="subtle">
								Default
							</Badge>
							<Badge v-if="account.disabled" theme="gray" variant="subtle">
								Disabled
							</Badge>
						</div>
					</div>

					<dl class="mt-3 grid gap-x-6 gap-y-4 sm:grid-cols-2">
						<div v-for="row in rowsFor(account)" :key="row.label">
							<dt class="text-p-sm text-ink-gray-5">{{ row.label }}</dt>
							<dd
								class="mt-0.5 truncate text-p-base"
								:class="row.value ? 'text-ink-gray-8' : 'text-ink-gray-4'"
							>
								{{ displayValue(row.value) }}
							</dd>
						</div>
					</dl>
				</li>
			</ul>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Alert, Badge, Button, ErrorMessage, Skeleton } from 'frappe-ui'
import {
	bankAccounts,
	bankAccountsError,
	bankAccountsLoaded,
	bankCan,
	bankPermissionsError,
	reloadBankAccounts,
	type BankAccount,
} from '@/data/bankAccounts'
import { displayValue } from '@/data/profile'
import AppPageHeader from '@/components/AppPageHeader.vue'

const loadError = computed(() => bankPermissionsError.value ?? bankAccountsError.value)

// Labelled here rather than read off the doctype: these are the five a person
// checks when they want to know where their pay lands, in that order. The
// policy decides which fields may leave the server (see `BANK_ACCOUNT`); this
// decides how the ones that do are read.
function rowsFor(account: BankAccount) {
	return [
		{ label: 'Bank', value: account.bank },
		{ label: 'Account number', value: account.bank_account_no },
		{ label: 'IBAN', value: account.iban },
		{ label: 'Branch code', value: account.branch_code },
		{ label: 'Account type', value: account.account_type },
	]
}
</script>
