/* WHAT A RESULT IS, IN A PERSON'S WORDS, AND WHAT MAY BE DONE WITH IT
 * (result navigation, part N-B). Pure: no React, no fetch, no browser.
 *
 * Every word here comes from the server's bounded result read
 * (`work/contract.ts`: ResultPage, ResultGroup, WorkResult). This module
 * decides nothing about the record. In particular:
 *
 *   NO PRIMARY IS GUESSED. There is no "the result", no newest-wins, no
 *   first-in-the-array, and no promotion by media type, file name, size or
 *   return order. Groups and items keep the server's own order, which is
 *   browsing order and says nothing about importance.
 *
 *   THE THREE PROVENANCE FACTS STAY APART. Returned by a run, attached to a
 *   post, and named by a claim are different facts with different wording,
 *   and a claim never makes its claimant the producer.
 *
 *   WHAT IS NOT THERE IS SAID. An unavailable result keeps its place with
 *   its reason; a group or item left off this page is counted, so zero
 *   never stands for "nobody looked". Opening is offered only where the
 *   server's own availability answer allows it. */
import { isAdmissionRef } from '../../refid'
import { stateWords } from '../../surfaces/sources/artifactOpener'
import type { Id } from '../../api'
import type { ResultBasis, ResultGroup, ResultPage, TurnLink, WorkResult } from '../../work/contract'

export { stateWords }

/* -- what one result is ---------------------------------------------------- */

/** Its label: what the record calls it, never a name invented here. */
export function itemLabel(item: WorkResult): string {
  const named = item.artifact?.name ?? item.inspection?.label ?? null
  const label = (named ?? '').trim()
  return label || item.ref
}

/** What kind of thing it is, in words. */
export function itemWhat(item: WorkResult): string {
  if (item.kind === 'artifact') return 'a held file'
  if (item.kind === 'post') return 'a post'
  return 'a record'
}

/** Bytes as the interface says them elsewhere (null stays silent). */
export function sizeWords(size: number | null | undefined): string | null {
  if (size == null || size < 0) return null
  if (size < 1024) return `${size} B`
  const k = size / 1024
  if (k < 1024) return `${k < 10 ? k.toFixed(1) : Math.round(k)} KB`
  const m = k / 1024
  return `${m < 10 ? m.toFixed(1) : Math.round(m)} MB`
}

/** One provenance fact in words. Each basis kind keeps its own sentence;
 *  `result-recovered` is said as what it was, not folded into a return. */
export function basisWords(b: ResultBasis): string {
  if (b.kind === 'returned-by-run')
    return b.observation === 'result-recovered' ? 'recovered as returned by this run' : 'returned by this run'
  if (b.kind === 'attached-to-turn') return 'attached to this post'
  return 'referenced by this claim'
}

/** Every provenance fact recorded for one result, in record order, each once.
 *  A result observed twice on the same post is one result with two facts. */
export function provenanceWords(item: WorkResult): string[] {
  const out: string[] = []
  for (const b of item.basis ?? []) {
    const words = basisWords(b)
    if (!out.includes(words)) out.push(words)
  }
  return out
}

/** How the association itself stands, where that needs saying. A reference
 *  somebody named is never drawn as this Work's own deliverable. */
export function associationWords(item: WorkResult): string | null {
  if (item.association === 'referenced') return 'referenced here; not verified as produced by this work'
  if (item.association === 'unverified') return 'the records disagree: this association is not verified'
  return null
}

/** Where it actually came from: the producing or attaching post, never a
 *  claim's post borrowed for it. */
export function sourceWords(source: TurnLink | null | undefined): string | null {
  if (!source) return null
  const where = source.conversation_name ?? null
  const number = source.number != null ? `#${source.number}` : null
  if (number && where) return `from ${number} in ${where}`
  if (number) return `from ${number}`
  return where ? `from ${where}` : null
}

/* -- whether it can be opened, and why not --------------------------------- */

/** Can this result be opened from here, and what to say when it cannot.
 *
 *  A HELD FILE opens only when the server's request-time check said the
 *  bytes are there: an actionable item with an `artifact` descriptor whose
 *  state is `held`. A listing is not a promise -- the opener resolves again
 *  -- but an unavailable descriptor is never offered.
 *
 *  A POST OR RECORD somebody named opens only when the inspection says both
 *  that it is available AND that it has somewhere to open (`opens`). A state
 *  of `ok` alone is not enough: an execution activity resolves and has no
 *  opener. */
export function openable(item: WorkResult): { can: boolean; why: string | null } {
  const no = (why: string) => ({ can: false, why })
  /* UNAVAILABLE KEEPS ITS OWN REASON. The server's word for this result, or
     the inspection's, or the descriptor's, before any wording of ours: a
     reader looking for a deleted post must read that it was deleted. */
  if (item.available === false)
    return no(item.reason ?? item.inspection?.why ?? item.artifact?.reason
      ?? stateWords(item.inspection?.state ?? item.artifact?.state))
  if (item.kind === 'artifact') {
    if (!item.actionable) return no(item.reason ?? 'not verified as produced or attached by this work')
    const a = item.artifact
    if (!a) return no(item.reason ?? 'the record holds no current answer about these bytes')
    if (!isAdmissionRef(item.ref)) return no('this is not an exact Admission reference')
    if (a.state !== 'held') return no(a.reason ?? stateWords(a.state))
    return { can: true, why: null }
  }
  const i = item.inspection
  if (!i) return no(item.reason ?? 'the record holds no current answer about this reference')
  if (!i.available) return no(i.why ?? stateWords(i.state))
  if (!i.opens) return no(i.why ?? 'there is nothing here that opens it')
  return { can: true, why: null }
}

/** The one line under a result: what it is, where it came from, what makes
 *  it this Work's, and -- when it cannot be opened -- why not. */
export function itemWords(item: WorkResult): string {
  const open = openable(item)
  const parts = [
    itemWhat(item),
    sizeWords(item.artifact?.size ?? null),
    sourceWords(item.source),
    ...provenanceWords(item),
    associationWords(item),
    open.can ? null : `cannot be opened here: ${open.why}`,
  ]
  return parts.filter((p): p is string => !!p).join(' · ')
}

/* -- a group ---------------------------------------------------------------- */

/** A group's heading: the post that produced it, or an honest statement that
 *  a return was never placed on one. No post is invented for it. */
export function groupHeading(group: ResultGroup): string {
  if (group.source) {
    const number = group.source.number != null ? `#${group.source.number}` : 'a post'
    const where = group.source.conversation_name
    return where ? `${number} in ${where}` : number
  }
  return 'A return with no post of its own'
}

/** Whether this group has a real source post to go to. */
export const hasSource = (group: ResultGroup): boolean => !!group.source

/** What is in this group and what is not: items shown, and the ones after
 *  this page counted rather than left at zero. */
export function groupCountWords(group: ResultGroup): string {
  const shown = group.items.length
  const total = Math.max(group.total_items, shown)
  if (group.omitted_items > 0) return `${shown} of ${total} results shown · ${group.omitted_items} more here`
  return total === 1 ? '1 result' : `${total} results`
}

/* -- a page ---------------------------------------------------------------- */

export interface Totals {
  /** groups the server says exist, before this page's bound */
  groups: number
  /** groups drawn now */
  shownGroups: number
  /** groups after this page */
  omittedGroups: number
  /** items drawn now */
  shownItems: number
  /** items the record associates that are not drawn now: the omitted tails
   *  of shown groups plus every item of the groups not shown */
  unseenItems: number
  /** every item the record associates, as far as the server counted */
  items: number
}

export function totalsOf(page: ResultPage): Totals {
  const shownGroups = page.groups.length
  let shownItems = 0
  let tails = 0
  for (const g of page.groups) {
    shownItems += g.items.length
    tails += Math.max(g.omitted_items, 0)
  }
  const unseenItems = tails + Math.max(page.omitted_group_items, 0)
  return {
    groups: Math.max(page.total_groups, shownGroups),
    shownGroups,
    omittedGroups: Math.max(page.omitted_groups, 0),
    shownItems,
    unseenItems,
    items: shownItems + unseenItems,
  }
}

/** The chooser's own summary line. Counts are structural: they say what the
 *  record associates, not how many files are readable today, and a group
 *  nobody has paged to is counted, never reported as empty. */
export function pageWords(page: ResultPage): string {
  const t = totalsOf(page)
  if (!t.groups && !t.items) return 'No results are recorded for this work yet'
  const first = t.omittedGroups > 0
    ? `${t.shownGroups} of ${t.groups} result groups`
    : `${t.groups} result ${t.groups === 1 ? 'group' : 'groups'}`
  const rest = t.unseenItems > 0
    ? `${t.shownItems} shown · ${t.unseenItems} more not listed here`
    : `${t.shownItems} ${t.shownItems === 1 ? 'result' : 'results'}`
  return `${first} · ${rest}`
}

/** The entry control's own words: results enough to say, bounds and all. */
export function entryWords(page: ResultPage): string {
  const t = totalsOf(page)
  if (!t.items) return 'No results recorded'
  return t.unseenItems > 0 ? `${t.shownItems}+ results` : `${t.items} ${t.items === 1 ? 'result' : 'results'}`
}

/** When this read's availability was checked. A record cursor describes
 *  structure; held bytes are only ever "as checked then". */
export function checkedWords(page: ResultPage): string | null {
  const at = (page.availability_checked_at ?? '').trim()
  return at ? `Availability checked ${at}` : null
}

/* -- more pages ------------------------------------------------------------- */

/** A read that failed. A refusal to page is never an empty result list. */
export interface ResultsRefresh {
  kind: 'ResultsRefreshRequired'
}

/** Whether a failed continuation read is the server's refresh condition
 *  (HTTP 409 `ResultsRefreshRequired`): the cursors moved or are foreign, so
 *  the only honest answer is to offer the first page again. */
export function isRefresh(e: unknown): boolean {
  if (!e || typeof e !== 'object') return false
  const o = e as Record<string, unknown>
  if (o.kind === 'ResultsRefreshRequired' || o.refresh_results === true) return true
  const inner = o.body ?? o.data ?? null
  if (inner && typeof inner === 'object') {
    const b = inner as Record<string, unknown>
    if (b.kind === 'ResultsRefreshRequired' || b.refresh_results === true) return true
  }
  return typeof o.message === 'string' && o.message.includes('ResultsRefreshRequired')
}

/** This page with an older page of groups added after it: the server's order
 *  kept, each group once by its exact id, counts taken from the newer read.
 *  Nothing is reordered and nothing is promoted. */
export function withOlderGroups(page: ResultPage, older: ResultPage): ResultPage {
  const seen = new Set<Id>(page.groups.map((g) => g.id))
  const added = older.groups.filter((g) => !seen.has(g.id))
  return {
    ...page,
    groups: [...page.groups, ...added],
    total_groups: Math.max(page.total_groups, older.total_groups),
    omitted_groups: Math.max(older.omitted_groups, 0),
    omitted_group_items: Math.max(older.omitted_group_items, 0),
    next_results_before: older.next_results_before,
    availability_checked_at: older.availability_checked_at || page.availability_checked_at,
  }
}

/** This page with one group's next items added: recorded order kept, each
 *  exact ref once, the group's own remaining count taken from the new read. */
export function withMoreItems(page: ResultPage, group: Id, more: ResultPage): ResultPage {
  const got = more.groups.find((g) => g.id === group) ?? null
  if (!got) return page
  return {
    ...page,
    groups: page.groups.map((g) => {
      if (g.id !== group) return g
      const seen = new Set<Id>(g.items.map((i) => i.ref))
      const items = [...g.items, ...got.items.filter((i) => !seen.has(i.ref))]
      return {
        ...g,
        items,
        total_items: Math.max(g.total_items, got.total_items, items.length),
        omitted_items: Math.max(got.omitted_items, 0),
        next_items_after: got.next_items_after,
      }
    }),
    availability_checked_at: more.availability_checked_at || page.availability_checked_at,
  }
}

/* -- the chooser's rows ----------------------------------------------------- */

/** One row of the chooser, in the order it is drawn. Flat, so one keyboard
 *  walk covers headings, source actions, results and the paging offers.
 *  `key` is what the row IS, not where it is: see `rowsOf`. */
export type ResultRow =
  | { row: 'group'; key: string; group: ResultGroup; heading: string; words: string; source: boolean }
  | { row: 'item'; key: string; group: ResultGroup; item: WorkResult; label: string; words: string; can: boolean; why: string | null }
  | { row: 'more-items'; key: string; group: ResultGroup; cursor: string; words: string }
  | { row: 'more-groups'; key: string; cursor: string; words: string }
  | { row: 'bounded'; key: string; words: string }

/** Every row of a page, in the server's order. `canPage` says whether the
 *  host lent a continuation read; without one the bound is still stated, so
 *  a reader is never told there is nothing more when there is.
 *
 *  A ROW IS IDENTIFIED BY WHAT IT IS, NEVER BY WHERE IT IS (independent
 *  mounted re-review ent-11d361574f9a, R4). A page grows while it is being
 *  read: a group gives up its remaining items, older groups arrive. A row
 *  identified by its place in the flat walk therefore changes identity
 *  whenever anything is added ABOVE it, and every later group's results are
 *  drawn again as different rows -- so a delayed page took the result a
 *  reader had chosen out of the document while that same result was still
 *  offered, and the keyboard was then recovered somewhere else entirely.
 *  An identity is the group and the exact reference the row is about. Where
 *  one page draws that same identity more than once -- the same file
 *  returned twice under one post, a group the read named twice -- each
 *  occurrence is numbered, so no two rows ever share a key. The numbering is
 *  per identity, so what one group gains leaves every other row's key alone.
 */
export function rowsOf(page: ResultPage, canPage: boolean): ResultRow[] {
  const rows: ResultRow[] = []
  const drawn = new Map<string, number>()
  const key = (what: string): string => {
    const n = drawn.get(what) ?? 0
    drawn.set(what, n + 1)
    return `${what}#${n}`
  }
  for (const group of page.groups) {
    rows.push({ row: 'group', key: key(`g:${group.id}`), group, heading: groupHeading(group), words: groupCountWords(group), source: hasSource(group) })
    for (const item of group.items) {
      const open = openable(item)
      rows.push({ row: 'item', key: key(`i:${group.id}:${item.ref}`), group, item, label: itemLabel(item), words: itemWords(item), can: open.can, why: open.why })
    }
    if (group.omitted_items > 0 && group.next_items_after && canPage)
      rows.push({ row: 'more-items', key: key(`mi:${group.id}`), group, cursor: group.next_items_after, words: `Show the other ${group.omitted_items} results here` })
    else if (group.omitted_items > 0)
      rows.push({ row: 'bounded', key: key(`b:${group.id}`), words: `${group.omitted_items} more results in this group are not listed here` })
  }
  const t = totalsOf(page)
  if (t.omittedGroups > 0 && page.next_results_before && canPage)
    rows.push({
      row: 'more-groups',
      key: key('mg'),
      cursor: page.next_results_before,
      words: `All results: ${t.omittedGroups} older ${t.omittedGroups === 1 ? 'group' : 'groups'}${page.omitted_group_items > 0 ? ` · ${page.omitted_group_items} more results` : ''}`,
    })
  else if (t.omittedGroups > 0)
    rows.push({ row: 'bounded', key: key('b:older-groups'), words: `${t.omittedGroups} older result groups are not listed here` })
  return rows
}
