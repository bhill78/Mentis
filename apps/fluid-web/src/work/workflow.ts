/* WHICH WORKFLOW GOVERNS A PIECE OF WORK, AS WORDS. Pure, so it is testable
 * without a DOM; `WorkflowSection.tsx` draws it.
 *
 * Everything said here is the server's (`/api/work/<id>` → `workflow`): the
 * current Workflow, how it came to govern the work, the activity progress the
 * work status computes, and every change with its reason and evidence. The
 * client decides nothing about it. A change is the owner's act, sent to
 * `/fluid/api/work/<id>/workflow`; it grants nothing and starts nothing. */

import type { WorkflowEvent, WorkflowRef, WorkflowView } from './contract'

const names = (refs: WorkflowRef[]) =>
  refs.map((r) => r.name ?? r.entry).join(', ') || 'none'

const by = (alias: string | null, id: string | null) =>
  alias ? `@${alias.replace(/^@/, '')}` : id ?? 'somebody unknown'

/** One line saying how the current Workflow came to govern the work. */
export function originWords(view: WorkflowView): string {
  const last = [...view.history].reverse().find((e) => e.kind === 'changed')
  switch (view.origin) {
    case 'named': return 'named when the work was asked'
    case 'continued': return 'carried from the request this continues'
    case 'changed':
      return last?.kind === 'changed'
        ? `changed by ${by(last.by_alias, last.by)} (${last.role})`
        : 'changed'
    case 'placed': return 'placed where the work runs; not named for it'
    case 'none': return 'no Workflow governs this work'
    default: return view.why_unknown ?? 'unknown'
  }
}

/** One history entry as a line: what it was, who, and from what to what. */
export function eventWords(e: WorkflowEvent): string {
  if (e.kind === 'asked') {
    const how = e.from === 'continued' ? 'carried from the request it continues'
      : e.workflows.length ? 'named' : 'asked with no Workflow named'
    return e.workflows.length
      ? `Asked with ${names(e.workflows)} · ${how}`
      : `Asked · ${how}`
  }
  return `${names(e.from)} → ${names(e.to)} · by ${by(e.by_alias, e.by)} (${e.role})`
}

/** An evidence reference as a reader is shown it: the post number where the
 *  server found one, else the reference. */
export function evidenceWords(ev: { ref: string; number?: number | null; act?: string | null }): string {
  if (ev.number !== null && ev.number !== undefined) return `#${ev.number}${ev.act ? ` (${ev.act})` : ''}`
  return ev.ref
}

/** One activity's state in words, from its children as the server lists them. */
export function activityWords(children: { state: string }[], said: string | null): string {
  if (!children.length) return said ?? 'nothing delegated for it'
  const counts = new Map<string, number>()
  for (const c of children) counts.set(c.state, (counts.get(c.state) ?? 0) + 1)
  return [...counts].map(([s, n]) => `${n} ${s.replaceAll('_', ' ').replaceAll('-', ' ')}`).join(' · ')
}

/** The references typed as evidence: ent-/opr- ids, split on spaces or
 *  commas, each once, a leading `#` allowed. Anything else is reported. */
export function parseEvidence(text: string): { refs: string[]; bad: string[] } {
  const refs: string[] = [], bad: string[] = []
  for (const raw of text.split(/[\s,]+/)) {
    const t = raw.trim().replace(/^#/, '')
    if (!t) continue
    if (/^(ent|opr)-[0-9a-f]{12}$/.test(t)) { if (!refs.includes(t)) refs.push(t) }
    else bad.push(raw)
  }
  return { refs, bad }
}

/** The body the owner's change sends, or why it cannot be sent yet. */
export function changeBody(workflow: string, because: string, evidence: string, op: string):
  { body: { workflow: string; because: string; evidence: string[]; op: string } } | { why: string } {
  if (!workflow) return { why: 'choose the Workflow to change to' }
  if (!because.trim()) return { why: 'say why the Workflow changes' }
  const { refs, bad } = parseEvidence(evidence)
  if (bad.length) return { why: `not a reference: ${bad.join(', ')} (ent- or opr- ids)` }
  if (!refs.length) return { why: 'cite at least one finding, result, decision or post' }
  return { body: { workflow, because: because.trim(), evidence: refs, op } }
}

/** The path the owner's change is sent to. */
export const changePath = (expectation: string) =>
  `/fluid/api/work/${encodeURIComponent(expectation)}/workflow`
