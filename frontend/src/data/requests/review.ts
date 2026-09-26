import { computed, reactive, ref, toValue, type MaybeRefOrGetter, type Ref } from 'vue'
import { dialog, toast } from 'frappe-ui'
import type { DecisionButton } from '../workflowStyle'
import {
  requestLabel,
  useApplyProcurementWorkflow,
  type AvailableWorkflowAction,
  type ProcurementRequestRow,
} from './procurement'

/**
 * Reviewing one request at a time, in a dialog, on the approvals pages.
 *
 * The lists used to carry the decision buttons themselves, and a button whose
 * outcome did not need confirming wrote it on the first click — a stray tap
 * while scrolling approved somebody's leave with nothing on screen to say it
 * had happened. So a list only opens a request now, and the decision is made
 * from the dialog: seen in full first, and written by a button pressed there.
 *
 * Three pieces, because the four pages share them in different combinations:
 * which row the dialog is showing (`useReviewTarget`, every page), settling a
 * leave application or an expense claim (`useRowDecision`), and applying a
 * procurement workflow transition (`useWorkflowAction`).
 */

/**
 * The row an open review dialog is showing.
 *
 * Held by name and looked up again in the list on every read, so a list that
 * refreshes under an open dialog — and every decision refreshes it — shows the
 * dialog the row as it now is rather than as it was when it was opened. The
 * row it was opened with stands in once the list no longer has it, and `gone`
 * says so: a request somebody else settled meanwhile should read as settled,
 * not offer the buttons it no longer accepts.
 */
export function useReviewTarget<Row extends { name: string }>(
  rows: MaybeRefOrGetter<Row[] | null | undefined>,
) {
  const open = ref(false)
  const opened = ref(null) as Ref<Row | null>

  const current = computed(() => {
    const name = opened.value?.name
    if (!name) return null
    return (toValue(rows) ?? []).find((row) => row.name === name) ?? null
  })

  const row = computed(() => current.value ?? opened.value)
  const gone = computed(() => Boolean(opened.value) && !current.value)

  function show(target: Row) {
    opened.value = target
    open.value = true
  }

  // Reactive, so a template reads `review.open` rather than `review.open.value`.
  return reactive({ open, row, gone, show })
}

/** The part of a `useCall` a decision needs: its submit, and why it failed. */
interface DecisionCall<Params, Result> {
  submit: (params: Params) => Promise<Result | null>
  error: unknown
}

export interface Confirmation {
  title: string
  message: string
  confirmLabel: string
}

/**
 * Settling one leave application or expense claim from its review dialog.
 *
 * Leave and expenses decided the same way twice, line for line; this is that
 * once. What differs between them is passed in: what the call is sent, what the
 * confirmation says, and what the toast says afterwards.
 */
export function useRowDecision<Row, Params, Result>(options: {
  call: DecisionCall<Params, Result>
  params: (row: Row, verdict: string) => Params
  confirmation: (row: Row, button: DecisionButton) => Confirmation
  succeeded: (row: Row, result: Result) => void
  /** After every decision that reached the server, whichever way it went. */
  settled: () => void
}) {
  // Holds the decision being written, so only the button that was pressed spins.
  const deciding = ref('')

  /** Whether the decision was written. The reason it was not is `call.error`,
   *  which the dialog renders. */
  async function submit(row: Row, verdict: string): Promise<boolean> {
    deciding.value = verdict
    try {
      // `submit` resolves null on failure rather than rejecting. Nothing is
      // thrown on from here: the button's click handler has nobody to hand a
      // rejection to, so it would only surface as an unhandled one, and the
      // reason is already on screen.
      const result = await options.call.submit(options.params(row, verdict))
      if (!result) return false
      options.succeeded(row, result)
      return true
    } finally {
      deciding.value = ''
      // On failure too: a refused decision may have been refused because the
      // row has moved on, and the dialog should show where it moved to.
      options.settled()
    }
  }

  async function decide(row: Row, button: DecisionButton, close: () => void) {
    // Whether an outcome needs confirming arrives with it. The row is written
    // with that decision on it, and that is not something the page can walk
    // back on the approver's behalf.
    if (button.confirm) {
      dialog.danger({
        ...options.confirmation(row, button),
        onConfirm: async () => {
          if (await submit(row, button.decision)) {
            close()
            return
          }
          // Thrown to the confirmation, which catches it and stays open with
          // the reason, rather than closing over a decision that did not happen.
          throw options.call.error ?? new Error('Could not save the decision')
        },
      })
      return
    }
    if (await submit(row, button.decision)) close()
  }

  return { deciding, decide }
}

/**
 * Applying a procurement workflow transition from a request's review dialog.
 *
 * Both procurement pages applied transitions with their own copy of this, and
 * the copies had drifted: one re-read the list after a refusal and the other
 * left the refused buttons on screen.
 */
export function useWorkflowAction(options: { settled: () => void }) {
  const call = useApplyProcurementWorkflow()

  // Holds the action being applied, so only the button that was pressed spins.
  const running = ref('')

  async function apply(
    request: ProcurementRequestRow,
    action: AvailableWorkflowAction,
    close: () => void,
  ) {
    running.value = action.action
    try {
      const result = await call.submit({
        doc: JSON.stringify({ doctype: 'Procurement Request', name: request.name }),
        // The action's own name, not the button's label: the label is what a
        // site could rename, and `apply_workflow` only knows the transition.
        action: action.action,
      })
      // Resolves null on failure; `call.error` renders the reason in the dialog.
      if (!result) return
      toast.success(`${action.action} applied to ${requestLabel(request)}`)
      close()
    } finally {
      // Once, here, rather than also on the success path: two overlapping
      // fetches abort each other, and a failed action still needs the list
      // re-read -- the state it was refused from may not be the one it is in.
      options.settled()
      running.value = ''
    }
  }

  return { call, running, apply }
}
