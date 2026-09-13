<template>
  <Combobox
    v-model="model"
    v-model:query="searchText"
    :options="options"
    :loading="search.loading"
    :filterable="false"
    trigger="button"
    :label="label"
    :description="description"
    :error="error"
    :required="required"
    :disabled="disabled"
    :placeholder="placeholder ?? `Select ${doctype.toLowerCase()}`"
    :empty-text="`No matching ${doctype.toLowerCase()}`"
    @update:query="(q) => runSearch(q as string)"
    @update:open="(isOpen) => onOpenChange(isOpen as boolean)"
  >
    <template #item-label="{ item }">
      <div class="min-w-0">
        <div class="truncate">{{ item.label }}</div>
        <div
          v-if="(item as LinkOption).sublabel"
          class="truncate text-p-sm text-ink-gray-5"
        >
          {{ (item as LinkOption).sublabel }}
        </div>
      </div>
    </template>
  </Combobox>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Combobox, useCall } from 'frappe-ui'
import { useDebounceFn } from '@vueuse/core'

interface LinkSearchResult {
  value: string
  label?: string
  description?: string
}

interface LinkOption {
  value: string
  label: string
  sublabel?: string
}

const props = defineProps<{
  /** The doctype to search. */
  doctype: string
  /** Filters forwarded to the link search, e.g. `{ company: 'Acme' }`. */
  filters?: Record<string, unknown>
  /**
   * A whitelisted server-side search query to use instead of the default
   * name search — the same `query` a desk Link field takes. Approver pickers
   * need one: the candidates come from the employee record and the department
   * tree, not from a filter over User.
   */
  query?: string
  /** Show the result's human-readable title above its stored ID. */
  titleFirst?: boolean
  label?: string
  description?: string
  error?: string
  required?: boolean
  disabled?: boolean
  placeholder?: string
}>()

const model = defineModel<string | null>()

const searchText = ref('')

// The same endpoint the desk's Link field uses, so a user sees the same
// candidates here as there — including the doctype's own search fields and
// any user permissions that narrow them.
const search = useCall<
  LinkSearchResult[],
  {
    doctype: string
    txt: string
    filters?: string
    query?: string
    page_length: number
  }
>({
  url: '/api/v2/method/frappe.desk.search.search_link',
  immediate: false,
})

const results = ref<LinkOption[]>([])

// The trigger renders the selected option's label, so a value the current
// query doesn't match still needs its label available. Anything seen once is
// kept for that.
const seen = ref(new Map<string, LinkOption>())

function toOption(result: LinkSearchResult): LinkOption {
  if (props.titleFirst) {
    const title = result.label && result.label !== result.value
      ? result.label
      : result.description || result.value
    return {
      value: result.value,
      label: title,
      sublabel: title !== result.value ? result.value : undefined,
    }
  }
  const label = result.label || result.value
  return {
    value: result.value,
    label,
    // `description` repeats the value when the doctype has no title field;
    // showing it then is just the id twice.
    sublabel:
      result.description && result.description !== label
        ? result.description
        : undefined,
  }
}

async function fetchOptions(txt: string) {
  const found = await search.submit({
    doctype: props.doctype,
    txt: txt ?? '',
    filters: props.filters ? JSON.stringify(props.filters) : undefined,
    query: props.query,
    page_length: 20,
  })
  // `submit` resolves null on failure; the error surfaces via search.error.
  if (!found) return
  results.value = found.map(toOption)
  for (const option of results.value) seen.value.set(option.value, option)
}

const runSearch = useDebounceFn(fetchOptions, 250)

const options = computed<LinkOption[]>(() => {
  const byValue = new Map<string, LinkOption>()
  for (const option of results.value) byValue.set(option.value, option)

  const selected = model.value
  if (selected && !byValue.has(selected)) {
    byValue.set(
      selected,
      seen.value.get(selected) ?? { value: selected, label: selected },
    )
  }
  return Array.from(byValue.values())
})

function onOpenChange(isOpen: boolean) {
  if (!isOpen) return
  // Binding `query` hands its ownership over, including the reset the
  // combobox would otherwise do on open — without it the committed label
  // stays in the search box and the next keystroke appends to it.
  searchText.value = ''
  fetchOptions('')
}

// A value that arrives from a loaded document (rather than from picking one)
// has no label yet. One lookup keeps the trigger from showing a bare id where
// the doctype has a title field.
watch(
  () => model.value,
  (value) => {
    if (value && !seen.value.has(value)) fetchOptions(value)
  },
  { immediate: true },
)

// The candidate set can depend on the filters, e.g. an approver list keyed to
// the employee it is for. Drop what the old filters returned so a stale list
// is never shown; the next open refetches.
watch(
  () => JSON.stringify(props.filters ?? {}),
  () => {
    results.value = []
  },
)
</script>
