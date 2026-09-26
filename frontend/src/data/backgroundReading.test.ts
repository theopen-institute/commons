import { describe, expect, it } from 'vitest'
import { pollReading, readingDeadlineMs, type JobState } from './backgroundReading'

/**
 * Waiting on a background reading. The failure this guards against is the
 * quiet one: a job the worker lost, and a dialog asking after it for an hour.
 */

type State = JobState<string> & { rows?: number }

/** A clock that moves only when the loop sleeps, and a server that answers
 *  from a script, repeating its last answer once the script runs out. */
function harness(answers: State[]) {
  let time = 0
  const asked: number[] = []
  return {
    now: () => time,
    sleep: async (ms: number) => {
      time += ms
    },
    check: async () => {
      asked.push(time)
      return answers.length > 1 ? answers.shift()! : answers[0]
    },
    asked,
  }
}

const messages = { deadlineMessage: 'Gave up.', failedMessage: 'Could not be read.' }

describe('pollReading', () => {
  it('passes each answer on and returns the result when done', async () => {
    const h = harness([{ status: 'queued' }, { status: 'reading', rows: 3 }, { status: 'done', result: 'read' }])
    const seen: State[] = []
    const result = await pollReading<string, State>({ ...h, ...messages, deadlineMs: 60_000, onProgress: (s) => seen.push(s) })
    expect(result).toBe('read')
    expect(seen.map((s) => s.status)).toEqual(['queued', 'reading', 'done'])
    expect(h.asked).toEqual([2000, 4000, 6000])
  })

  it("throws the server's sentence when the reading failed", async () => {
    const h = harness([{ status: 'failed', error: 'Claude declined to read this document.' }])
    await expect(pollReading<string, State>({ ...h, ...messages, deadlineMs: 60_000 })).rejects.toThrow('Claude declined')
  })

  it('has words of its own when the server gave none', async () => {
    const h = harness([{ status: 'failed' }])
    await expect(pollReading<string, State>({ ...h, ...messages, deadlineMs: 60_000 })).rejects.toThrow('Could not be read.')
  })

  it('gives up at the deadline on a reading that never ends', async () => {
    const h = harness([{ status: 'reading' }])
    await expect(pollReading<string, State>({ ...h, ...messages, deadlineMs: 10_000 })).rejects.toThrow('Gave up.')
    expect(h.asked.at(-1)).toBe(10_000)
  })

  it('returns null, without asking, once the caller has gone', async () => {
    const h = harness([{ status: 'reading' }])
    let gone = false
    const waiting = pollReading<string, State>({ ...h, ...messages, deadlineMs: 60_000, cancelled: () => gone })
    gone = true
    expect(await waiting).toBeNull()
    expect(h.asked).toEqual([])
  })

  it('stops when a question to the server fails', async () => {
    const h = harness([{ status: 'reading' }])
    const check = async () => {
      throw new Error('That reading is not available. Start it again.')
    }
    await expect(pollReading<string, State>({ ...h, ...messages, check, deadlineMs: 60_000 })).rejects.toThrow('not available')
  })
})

describe('readingDeadlineMs', () => {
  it('outlasts a full wait in the queue and a full run, each with the server margin', () => {
    // The server reports failure 60 s past the job timeout, in the queue or
    // running, so its own sentence should always come first.
    expect(readingDeadlineMs(720)).toBeGreaterThan(2 * (720 + 60) * 1000)
    // And well under the hour the cache keeps a reading for.
    expect(readingDeadlineMs(720)).toBeLessThan(3600 * 1000)
  })
})
