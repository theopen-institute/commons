<template>
  <!-- No `message` prop: it only renders as the default slot's fallback, so a
       dialog with content of its own has to place that line itself. -->
  <Dialog v-model:open="open" title="Request leave" :actions="actions">
    <div class="space-y-4">
      <p class="text-p-base text-ink-gray-6">
        Your approver is notified once you send this.
      </p>
      <LinkControl
        v-model="form.leave_type"
        doctype="Leave Type"
        label="Leave type"
        :error="errors.leave_type"
        required
      />

      <div
        v-if="selectedBalance"
        class="flex items-baseline justify-between rounded-4 bg-surface-gray-2 px-3 py-2"
      >
        <span class="text-p-sm text-ink-gray-6">Balance</span>
        <span class="text-base-medium text-ink-gray-8">
          {{ selectedBalance.remaining_leaves }} day{{
            selectedBalance.remaining_leaves === 1 ? '' : 's'
          }}
          <span
            v-if="selectedBalance.leaves_pending_approval"
            class="text-p-sm font-normal text-ink-gray-5"
          >
            · {{ selectedBalance.leaves_pending_approval }} pending
          </span>
        </span>
      </div>

      <div class="grid gap-4 sm:grid-cols-2">
        <BikramDatePicker
          v-model="form.from_date"
          label="From"
          :error="errors.from_date"
          required
        />
        <BikramDatePicker
          v-model="form.to_date"
          label="To"
          :error="errors.to_date"
          required
        />
      </div>

      <FormControl
        v-model="form.half_day"
        type="checkbox"
        label="Half day"
        :disabled="!form.from_date || !form.to_date"
      />
      <BikramDatePicker
        v-if="form.half_day && form.from_date !== form.to_date"
        v-model="form.half_day_date"
        label="Which day is the half day"
        :error="errors.half_day_date"
      />

      <p v-if="dayCountLabel" class="text-p-sm text-ink-gray-6">
        {{ dayCountLabel }}
      </p>

      <FormControl
        v-model="form.description"
        type="textarea"
        label="Reason"
        :rows="3"
        placeholder="Optional, but it helps your approver decide."
      />

      <LinkControl
        v-model="form.leave_approver"
        doctype="User"
        label="Approver"
        :query="leaveCan.approver_query"
        :filters="{ employee: employee.name, doctype: 'Leave Application' }"
        :error="errors.leave_approver"
        description="Set from your employee record. Ask HR if the right person isn't listed."
        :required="leaveCan.approver_mandatory"
      />

      <ErrorMessage v-if="request.error" :message="request.error.message" />
    </div>
  </Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import {
  Dialog,
  ErrorMessage,
  FormControl,
  toast,
  type DialogAction,
} from 'frappe-ui'
import { useDebounceFn } from '@vueuse/core'
import BikramDatePicker from './BikramDatePicker.vue'
import LinkControl from './LinkControl.vue'
import {
  leaveCan,
  useLeaveDayCount,
  useRequestLeave,
  type LeaveAllocationSummary,
  type MyEmployee,
} from '@/data/requests/leave'

const props = defineProps<{
  employee: MyEmployee
  balances: Record<string, LeaveAllocationSummary>
}>()

const open = defineModel<boolean>('open', { required: true })

const emit = defineEmits<{ created: [name: string] }>()

/**
 * What this form collects.
 *
 * Not a Leave Application document. `request_leave` takes the fields a request
 * may set and fills in the rest — the employee from the session, the naming
 * series, the posting date and the initial state from the doctype — so a site
 * that customises any of them gets what it configured. A form that posted a
 * document would be deciding all of that here instead.
 */
interface LeaveForm {
  leave_type: string
  from_date: string
  to_date: string
  half_day: boolean
  half_day_date: string
  description: string
  leave_approver: string
}

function blankForm(): LeaveForm {
  return {
    leave_type: '',
    from_date: '',
    to_date: '',
    half_day: false,
    half_day_date: '',
    description: '',
    leave_approver: props.employee.leave_approver ?? '',
  }
}

const form = reactive<LeaveForm>(blankForm())
const request = useRequestLeave()

const submitAttempted = ref(false)

const selectedBalance = computed(() =>
  form.leave_type ? props.balances[form.leave_type] : undefined,
)

const problems = computed(() => {
  const found: Record<string, string> = {}
  if (!form.leave_type) found.leave_type = 'Pick a leave type'
  if (!form.from_date) found.from_date = 'Pick a start date'
  if (!form.to_date) found.to_date = 'Pick an end date'
  if (form.from_date && form.to_date && form.to_date < form.from_date) {
    found.to_date = 'The end date is before the start date'
  }
  // Mandatory is HR Settings' answer, not this form's: a site that made the
  // approver optional is one where a blank field has to be allowed through.
  if (leaveCan.value.approver_mandatory && !form.leave_approver) {
    found.leave_approver = 'Pick an approver'
  }
  if (form.half_day && form.from_date !== form.to_date && !form.half_day_date) {
    found.half_day_date = 'Pick which day is the half day'
  }
  return found
})

const errors = computed(() => (submitAttempted.value ? problems.value : {}))

// HRMS owns what a date range costs — it subtracts holidays per leave type and
// handles the half day. Recomputing it here would drift from what gets booked.
const dayCount = useLeaveDayCount()

const countDays = useDebounceFn(() => {
  if (problems.value.from_date || problems.value.to_date || !form.leave_type) {
    return
  }
  dayCount.submit({
    employee: props.employee.name,
    leave_type: form.leave_type,
    from_date: form.from_date,
    to_date: form.to_date,
    half_day: form.half_day ? 1 : 0,
    half_day_date: form.half_day_date || undefined,
  })
}, 300)

watch(
  () => [
    form.leave_type,
    form.from_date,
    form.to_date,
    form.half_day,
    form.half_day_date,
  ],
  () => countDays(),
)

const dayCountLabel = computed(() => {
  const days = dayCount.data
  if (days == null) return ''
  if (days <= 0) return 'That range is all holidays — no leave would be booked.'
  return `${days} day${days === 1 ? '' : 's'} of leave.`
})

// A dialog that keeps the last request's values is a trap: the next one starts
// half-filled with dates that have passed.
watch(open, (isOpen) => {
  if (isOpen) return
  Object.assign(form, blankForm())
  submitAttempted.value = false
  dayCount.reset()
})

async function send(close: () => void) {
  submitAttempted.value = true
  if (Object.keys(problems.value).length) return

  try {
    const created = await request.submit({ doc: JSON.stringify(form) })
    // `submit` resolves null on failure; the reason renders inline.
    if (!created) return
    toast.success('Leave requested')
    emit('created', created.name)
    close()
  } catch {
    // `request.error` renders the server's reason inline — an overlapping
    // application or an insufficient balance is worth reading in full.
  }
}

const actions = computed<DialogAction[]>(() => [
  {
    label: 'Send request',
    variant: 'solid',
    onClick: ({ close }) => send(close),
  },
])
</script>
