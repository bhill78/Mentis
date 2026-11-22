/* THE SEAM BETWEEN THE CHOOSER'S WIRE SHAPE AND THE OPENER'S DESTINATION.
 *
 * HOST-INTEGRATION.md §3.3 left this to whoever mounts the two parts
 * together: the chooser (`results/host.ts`) hands its host the server's exact
 * `WorkResult` and the group it was chosen from, and the opener
 * (`results/targets.ts`, `results/mount.ts`) takes a `ResultDestination`.
 * Neither part may reach into the other's schema, so the conversion lives
 * here, in the integrator's own module, and is checked on its own
 * (`tests/quiet2_results_from_work_unit.ts`).
 *
 * Three rules it keeps, because they are the ones the review of the chooser's
 * own words established:
 *
 *   NOTHING IS INFERRED. The route is the server's `inspection.opens`, the
 *   availability its `inspection.state` (or an artifact descriptor's own
 *   `state`), and the reason its own words. A file name, a media type and a
 *   label decide nothing.
 *
 *   PROVENANCE IS CARRIED, NOT RESTATED. `basis` and `association` come
 *   across exactly, so `actionable()` and `REFERENCED_ONLY` keep meaning what
 *   they mean: a claim that merely names a reference is not a deliverable.
 *
 *   THE PRODUCING POST IS THE SOURCE. A result's `source` Turn is where the
 *   bytes came from; where the record states none, there is none -- it is
 *   never borrowed from the post the chooser happens to be drawn on.
 */
import type { Id } from '../../api'
import type { PostResults, PostResultsLookup } from './host'
import { destinationOfRef, type Basis, type ResultDestination, type ResultTarget } from './targets'
import type { ResultGroup, WorkItem, WorkResult } from '../../work/contract'

/** THE EXACT WIRE ITEM AS A DESTINATION. `work` and `group` are the chooser's
 *  own answer about where the press came from and are passed through so a
 *  history entry and a later re-read name the same group the reader chose. */
export function destinationOfResult(
  item: WorkResult,
  over: { work?: Id | null; group?: Id | null } = {},
): ResultDestination {
  const i = item.inspection
  const a = item.artifact
  /* AN ARTIFACT DESCRIPTOR'S OWN WORD IS ITS AVAILABILITY (`held` is `ok`,
     `availabilityOf`); a reference the server inspected answers with its
     inspection. Where it answered neither, nothing is claimed: `unknown`
     degrades to `unreadable` and the press is refused with the server's
     reason rather than attempted. */
  const state = i?.state ?? a?.state ?? 'unknown'
  const available = i ? i.available : a ? a.state === 'held' : false
  return destinationOfRef({
    id: item.ref,
    type: item.kind,
    label: i?.label ?? a?.name ?? null,
    available,
    state,
    why: i?.why ?? a?.reason ?? item.reason ?? null,
    /* a descriptor with no inspection is held bytes, which is the one route
       its own shape establishes; anything else is the server's `opens` */
    opens: i?.opens ?? (a ? 'file' : null),
    post: i?.post ?? null,
    conversation: i?.conversation ?? null,
    file: a ? { state: a.state, name: a.name ?? null, size: a.size ?? null, claimed_media_type: a.claimed_media_type ?? null } : null,
  }, {
    work: over.work ?? null,
    group: over.group ?? null,
    basis: item.basis.map((b) => b.kind as Basis),
    verified: item.association === 'verified',
    /* WHERE IT CAME FROM, and only where the record says so */
    source: item.source ? { kind: 'post', conversation: item.source.conversation, post: item.source.turn } : null,
  })
}

/** A STORED HISTORY ENTRY'S TARGET, BACK AS A DESTINATION (`ResultPage`'s
 *  `destinationOfTarget`, HOST-INTEGRATION.md §3.2). The entry holds the
 *  identity the reader opened, not the facts about it: those are read again at
 *  the press (the mandatory fresh read, B4.1, and P4's own re-read), which is
 *  what decides whether it still opens. So this says what the entry points
 *  at and leaves availability to that read -- it never asserts the thing is
 *  still there, and a target with no viewer to restore (a URL, a commit) has
 *  no destination here at all. */
export function destinationOfTarget(t: ResultTarget): ResultDestination | null {
  if (t.kind === 'artifact') {
    return destinationOfRef({ id: t.ref, type: 'file', available: true, state: 'held', opens: 'file' })
  }
  if (t.kind === 'post') {
    return destinationOfRef({ id: t.post, type: 'post', available: true, state: 'ok', opens: 'post', conversation: t.conversation, post: t.post })
  }
  if (t.kind === 'record') {
    return destinationOfRef({ id: t.ref, type: 'record', available: true, state: 'ok', opens: 'record' })
  }
  return null
}

/** Whether a page holds anything at all to offer. A Work with a result read
 *  that came back empty gets no chooser: an empty section is noise. */
const holdsAnything = (groups: readonly ResultGroup[] | undefined): boolean =>
  !!groups?.some((g) => g.items.length > 0)

/** WHICH POSTS CARRY WHICH WORK'S RESULTS, from the overview the server
 *  already answers for a conversation (`/api/work?conversation=`).
 *
 *  The mapping is the record's, exactly: a Work's `origin` Turn is its
 *  request, and each of its `update_turns` is a recorded carrier update. No
 *  author, nearest reply or expectation is consulted, which is the one thing
 *  `results/host.ts` says the chooser must never be handed a guess about. */
export function resultsByPost(o: { items?: readonly WorkItem[] } | null | undefined): Map<Id, PostResults[]> {
  const out = new Map<Id, PostResults[]>()
  const add = (post: Id | null | undefined, r: PostResults) => {
    if (!post) return
    const had = out.get(post) ?? []
    if (had.some((x) => x.work === r.work && x.mapping === r.mapping)) return
    had.push(r); out.set(post, had)
  }
  for (const it of o?.items ?? []) {
    const page = it?.result_summary
    if (!it?.expectation || !page || !holdsAnything(page.groups)) continue
    add(it.origin?.turn, { work: it.expectation, title: it.title ?? null, mapping: 'request', page })
    for (const u of it.update_turns ?? []) add(u?.turn, { work: it.expectation, title: it.title ?? null, mapping: 'update', page })
  }
  return out
}

/** The lookup `Post.tsx` asks (`PostPage.results.of`), over one read. */
export const lookupOf = (o: { items?: readonly WorkItem[] } | null | undefined): PostResultsLookup => {
  const byPost = resultsByPost(o)
  return (post) => byPost.get(post) ?? []
}
