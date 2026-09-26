/**
 * Asking after a document being read in a background job, until it is done.
 *
 * Invoices (`capture.ts`) and bank statements (`ReconciliationImportDialog.vue`)
 * are both read by Claude in the server's `long` queue, because a read can
 * outlast a web request, and the browser holds only a token. See
 * `commons.api_integrations.claude.jobs`. This is the browser's half: ask
 * every few seconds, pass each answer on for the progress line, and stop on
 * `done`, on `failed`, when the caller has moved on, or at a deadline.
 *
 * ## Why a deadline of its own
 *
 * The server already reports a reading as failed once its job has run past
 * RQ's timeout, or waited in the queue as long. The deadline here is the
 * backstop for when that answer never comes: a reading started before the
 * server kept the times, or a server that keeps answering "reading" for any
 * other reason. It is set past the longest the server could legitimately take
 * to say so (a full wait in the queue, then a full run), so that the server's
 * own sentence, which says more, arrives first whenever there is one.
 *
 * Pure but for the clock and the timer, which are injectable so the loop can
 * be tested without waiting.
 */

export interface JobState<Result> {
  status: 'queued' | 'reading' | 'done' | 'failed'
  result?: Result
  error?: string
}

/** How often the browser asks after a reading. */
export const POLL_MS = 2000

/** The server's grace past a job's timeout before it calls the job lost
 *  (`jobs.MARGIN`). */
const SERVER_MARGIN_S = 60

/**
 * How long the browser waits on a job whose RQ timeout is `jobTimeoutS`,
 * the server's `JOB_TIMEOUT`: the longest wait in the queue and the longest
 * run the server allows, each with its margin, and a minute more for the
 * answer to arrive.
 */
export function readingDeadlineMs(jobTimeoutS: number): number {
  return (2 * (jobTimeoutS + SERVER_MARGIN_S) + 60) * 1000
}

export interface PollOptions<State> {
  /** Ask the server once. A rejection ends the wait with that error. */
  check: () => Promise<State>
  /** Milliseconds after which to give up, counted from the call. */
  deadlineMs: number
  /** The sentence for giving up at the deadline. */
  deadlineMessage: string
  /** The sentence for a failure the server gave no words for. */
  failedMessage: string
  /** Told every answer, for the progress line. */
  onProgress?: (state: State) => void
  /** Whether whoever was waiting has gone: a closed dialog, a new file. */
  cancelled?: () => boolean
  intervalMs?: number
  now?: () => number
  sleep?: (ms: number) => Promise<void>
}

/**
 * The reading's result, once the job is done.
 *
 * Throws with the server's sentence when the reading failed, and with
 * `deadlineMessage` at the deadline. Returns null when `cancelled` says the
 * wait is over: the job carries on regardless, and its answer is simply not
 * collected.
 */
export async function pollReading<Result, State extends JobState<Result>>(
  options: PollOptions<State>,
): Promise<Result | null> {
  const {
    check,
    deadlineMs,
    deadlineMessage,
    failedMessage,
    onProgress,
    cancelled = () => false,
    intervalMs = POLL_MS,
    now = Date.now,
    sleep = (ms) => new Promise((resolve) => window.setTimeout(resolve, ms)),
  } = options
  const deadline = now() + deadlineMs
  for (;;) {
    await sleep(intervalMs)
    if (cancelled()) return null
    const state = await check()
    if (cancelled()) return null
    onProgress?.(state)
    if (state.status === 'done' && state.result !== undefined) return state.result
    if (state.status === 'failed') throw new Error(state.error || failedMessage)
    if (now() >= deadline) throw new Error(deadlineMessage)
  }
}
