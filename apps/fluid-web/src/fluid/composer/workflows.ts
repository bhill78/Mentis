/* WORKFLOWS IN THE `/` PALETTE: what is offered, how it is filtered, and what
 * picking one does to the draft. Pure, so it is testable without a DOM; the
 * read itself is `useWorkflows.ts`.
 *
 * Picking attaches the Workflow the way the "Use…" picker does: its id goes
 * into `draft.use.governed`, its name into `draft.use.said` for the chip, and
 * `bodyOf` sends it as `governed` wherever it sends it today. Nothing new is
 * sent and nothing is placed. */

import type { Draft } from '../../composer/draft'
import type { Trigger } from '../../composer/trigger'

/** One established Workflow, as the governed register lists it. */
export interface WorkflowRow { entry: string; name: string }

/** Rows of `/fluid/api/governed?state=standing&kind=workflow`: `summary` is
 *  the Workflow's first declared field, its name. Rows without one are left
 *  out, since there is nothing to type to find them. */
export function workflowsOf(got: { groups?: Record<string, { entry: string; kind?: string; summary?: string; governs?: boolean }[]> } | null): WorkflowRow[] {
  return (got?.groups?.standing ?? [])
    .filter((r) => r.governs !== false && !!r.summary?.trim())
    .map((r) => ({ entry: r.entry, name: r.summary!.trim() }))
}

/** What follows the `/`, matched case-insensitively as a substring of the name. */
export function matchWorkflows(list: WorkflowRow[], query: string): WorkflowRow[] {
  const q = query.replace(/^\//, '').trim().toLowerCase()
  return q ? list.filter((w) => w.name.toLowerCase().includes(q)) : list
}

/** The draft with the Workflow attached. Already attached: unchanged in its
 *  list (never twice); removing it stays on the chip's ×. */
export function attachWorkflow(d: Draft, w: WorkflowRow): Draft {
  const governed = d.use?.governed ?? []
  return {
    ...d,
    use: {
      governed: governed.includes(w.entry) ? governed : [...governed, w.entry],
      said: { ...d.use?.said, [w.entry]: w.name },
    },
  }
}

/** The text without the `/…` token, and where the caret goes. One space is
 *  kept where the token sat between two words. */
export function dropToken(text: string, t: Pick<Trigger, 'start' | 'end'>): { text: string; caret: number } {
  const before = text.slice(0, t.start)
  let after = text.slice(t.end)
  if ((before === '' || /\s$/.test(before)) && after.startsWith(' ')) after = after.slice(1)
  return { text: before + after, caret: before.length }
}
