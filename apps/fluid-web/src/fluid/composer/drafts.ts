/* A DRAFT OUTLIVES THE SURFACE IT IS WRITTEN IN (#117: switching presentation
 * keeps drafts). Each composer has a place -- the conversation, or one thread
 * in it -- and what is written there is kept for this tab: going full screen,
 * into conversation focus, pinning or unpinning a thread, or reloading, the
 * words are still there. Attachments are not kept: their staged bytes belong
 * to the moment they were attached, and a reload would show a chip for
 * something the page no longer holds. */

import { emptyDraft, type Draft } from '../../composer/draft'

const KEY = (where: string) => 'mentis:fluid:draft:' + where
const held = new Map<string, Draft>()

export function loadDraft(where: string): Draft {
  const had = held.get(where)
  if (had) return had
  try {
    const raw = sessionStorage.getItem(KEY(where))
    if (raw) return { ...emptyDraft(), ...(JSON.parse(raw) as Draft), attached: [] }
  } catch { /* nothing kept */ }
  return emptyDraft()
}

export function saveDraft(where: string, d: Draft) {
  held.set(where, d)
  try {
    if (!d.text.trim() && !d.to.length && !d.refs?.length) sessionStorage.removeItem(KEY(where))
    else sessionStorage.setItem(KEY(where), JSON.stringify({ ...d, attached: [] }))
  } catch { /* kept in memory only */ }
}

export function dropDraft(where: string) {
  held.delete(where)
  try { sessionStorage.removeItem(KEY(where)) } catch { /* nothing kept */ }
}
