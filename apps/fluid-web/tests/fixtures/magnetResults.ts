/* THE FROZEN MAGNET TOPOLOGY, as the bounded result read answers it
 * (handoff checks F1 and F2). A fixture, not a live read: the trunk
 * `opr-9548d7a9c1f7` as the navigation review froze it -- request #20,
 * returns on #37, #61, #80 and #88, review #91, the mapped carrier update
 * #92, and follow-up activity through #99 including the #97 return.
 *
 * It is shaped by `src/work/contract.ts` (ResultPage / ResultGroup /
 * WorkResult), the structural projection's own wire types, so the chooser is
 * checked against the interface it will actually be given. Nothing here
 * reads a Brain, and no live Work was touched to make it.
 *
 * The three files of #88 are the ones the review named, and the point of the
 * fixture: they must stay exactly reachable however much review and status
 * activity came after them.
 *
 * Also here, because they are what breaks a chooser: a return observed twice
 * on one post, an unplaced return with no post of its own, a claim that
 * merely names somebody else's artifact, bytes that are purged and bytes
 * that do not match, a reference that resolves but has nothing to open, and
 * more groups and items than either compact cap. */
import type { ResultGroup, ResultPage, TurnLink, WorkResult } from '../../src/work/contract'

export const WORK = 'opr-9548d7a9c1f7'
export const CONVERSATION = 'ent-magnetconv01'
const WHERE = 'Yellow Quiet Magnet'

/** #88's three files, named by the navigation review. */
export const GEN3 = ['adm-667a23eb07a8', 'adm-a43714dc1b5b', 'adm-cf3b99ac05cd'] as const

export const turn = (number: number, id = `ent-t${number}`): TurnLink =>
  ({ turn: id, number, conversation: CONVERSATION, conversation_name: WHERE })

/** A held file this Work returned: the ordinary, openable case. */
export const returned = (ref: string, name: string, at: TurnLink, size = 182_244): WorkResult => ({
  ref, kind: 'artifact', source: at,
  basis: [{ kind: 'returned-by-run', act: `opr-act-${ref.slice(4, 10)}`, work: WORK, turn: at.turn, observation: 'result-returned' }],
  association: 'verified', actionable: true, reason: null, available: true,
  artifact: { ref, state: 'held', name, size, claimed_media_type: name.endsWith('.png') ? 'image/png' : 'text/markdown' },
})

/** The same file, observed as returned and then recovered on the same post:
 *  one result with two facts, never two files. */
export const twiceObserved = (ref: string, name: string, at: TurnLink): WorkResult => ({
  ...returned(ref, name, at),
  basis: [
    { kind: 'returned-by-run', act: 'opr-act-ret-61', work: WORK, turn: at.turn, observation: 'result-returned' },
    { kind: 'returned-by-run', act: 'opr-act-rec-61', work: WORK, turn: at.turn, observation: 'result-recovered' },
  ],
})

/** Bytes the record still lists and cannot give: visible, with its reason. */
export const purged = (ref: string, name: string, at: TurnLink): WorkResult => ({
  ref, kind: 'artifact', source: at,
  basis: [{ kind: 'returned-by-run', act: 'opr-act-purged', work: WORK, turn: at.turn, observation: 'result-returned' }],
  association: 'verified', actionable: true, available: false, reason: 'its bytes were purged on 2026-11-12',
  artifact: { ref, state: 'purged', name, reason: 'its bytes were purged on 2026-11-12' },
})

/** Held by the record, bytes that do not match what was admitted. */
export const corrupt = (ref: string, name: string, at: TurnLink): WorkResult => ({
  ref, kind: 'artifact', source: at,
  basis: [{ kind: 'attached-to-turn', act: 'opr-act-attach', work: WORK, turn: at.turn }],
  association: 'verified', actionable: true, available: true, reason: null,
  artifact: { ref, state: 'held-but-corrupt', name, size: 4096 },
})

/** AN ARTIFACT A CLAIM MERELY NAMED. No producer, no metadata, no action: the
 *  claim is a fact about the claim, and the owner's broad artifact access is
 *  not a licence to promote it. */
export const claimedOnly = (ref: string, at: TurnLink): WorkResult => ({
  ref, kind: 'artifact', source: null,
  basis: [{ kind: 'authored-result-ref', act: 'opr-act-claim', work: WORK, turn: at.turn }],
  association: 'referenced', actionable: false,
  reason: 'named by this work\'s outcome claim; not verified as produced or attached here',
})

/** An exact post somebody referenced: a reference, not produced bytes. */
export const postRef = (id: string, at: TurnLink, number: number): WorkResult => ({
  ref: id, kind: 'post', source: at,
  basis: [{ kind: 'authored-result-ref', act: 'opr-act-postref', work: WORK, turn: at.turn }],
  association: 'referenced', actionable: false, reason: null, available: true,
  inspection: { id, state: 'ok', available: true, opens: 'post', why: null, post: id, conversation: CONVERSATION, label: `the comparison post #${number}` },
})

/** A record that resolves and has nowhere to open: an execution activity.
 *  `state: 'ok'` alone must not be read as openable. */
export const openlessRecord = (id: string, at: TurnLink): WorkResult => ({
  ref: id, kind: 'record', source: at,
  basis: [{ kind: 'authored-result-ref', act: 'opr-act-exe', work: WORK, turn: at.turn }],
  association: 'referenced', actionable: false, reason: null, available: true,
  inspection: { id, state: 'ok', available: true, opens: null, why: 'this Brain has no opener for an execution activity', label: 'a run of @Magnet-Builder' },
})

/** A post that was deleted since it was named. */
export const deletedPost = (id: string, at: TurnLink): WorkResult => ({
  ref: id, kind: 'post', source: at,
  basis: [{ kind: 'authored-result-ref', act: 'opr-act-gone', work: WORK, turn: at.turn }],
  association: 'referenced', actionable: false, reason: null, available: false,
  inspection: { id, state: 'deleted', available: false, opens: null, why: 'this post was deleted' },
})

export const group = (id: string, items: WorkResult[], more: Partial<ResultGroup> = {}): ResultGroup => ({
  id, source: null, unplaced: false, items,
  total_items: items.length, omitted_items: 0, next_items_after: null, ...more,
})

const page = (groups: ResultGroup[], more: Partial<ResultPage> = {}): ResultPage => ({
  groups, total_groups: groups.length, omitted_groups: 0, omitted_group_items: 0,
  next_results_before: null, availability_checked_at: '2026-11-21T21:40:00Z', ...more,
})

/* -- F1: the compact overview page, #88 within the cap -------------------- */

const T97 = turn(97), T92 = turn(92), T91 = turn(91), T88 = turn(88), T80 = turn(80), T61 = turn(61), T37 = turn(37)

/** The newest groups first, exactly as the server ordered them: the #97
 *  follow-up return, the #91 review, #88's three files, and the older
 *  generations. #92 is the mapped carrier update; it carries the chooser,
 *  and the chooser's groups are the Work's own producing posts. */
export const overview: ResultPage = page([
  group('grp-97', [returned('adm-97aa11bb22cc', 'needs-you-repair-report.md', T97, 24_118)], { source: T97 }),
  group('grp-91', [
    returned('adm-91aa11bb22cc', 'magnet-review-gen3.md', T91, 41_002),
    openlessRecord('ent-exe91review01', T91),
  ], { source: T91 }),
  group('grp-88', [
    returned(GEN3[0], 'g3a-yellow-puck.png', T88),
    returned(GEN3[1], 'g3b-yellow-puck.png', T88),
    returned(GEN3[2], 'gen3-comparison.html', T88, 639_715),
    postRef('ent-p88compare01', T88, 88),
  ], { source: T88, total_items: 5, omitted_items: 1, next_items_after: 'items:grp-88:4' }),
  group('grp-80', [returned('adm-80aa11bb22cc', 'gen2-comparison.html', T80, 412_880), corrupt('adm-80bb22cc33dd', 'gen2-notes.md', T80)], { source: T80 }),
  group('grp-61', [twiceObserved('adm-61aa11bb22cc', 'gen1-puck.png', T61)], { source: T61 }),
  group('grp-37', [returned('adm-37aa11bb22cc', 'magnet-read-model.md', T37, 18_902), purged('adm-37bb22cc33dd', 'early-sketch.png', T37)], { source: T37 }),
  group('grp-unplaced-1', [returned('adm-unpl11bb22cc', 'unplaced-return.md', turn(0, 'ent-none'), 2_048)], { unplaced: true, source: null }),
  group('grp-claim', [claimedOnly('adm-ff0011223344', T92), deletedPost('ent-p0goneaway01', T92)], { source: T92 }),
], {
  total_groups: 11, omitted_groups: 3, omitted_group_items: 9, next_results_before: 'groups:before:grp-37',
})

/* -- F2: more groups and items than either cap, #88 below the fold -------- */

/** The newest eight groups, all of them later review and status activity:
 *  #88 is NOT here. This is the case the review named -- a compact chooser
 *  filled by later rounds -- and the older page below must still reach it. */
export const crowdedFirstPage: ResultPage = page(
  Array.from({ length: 8 }, (_, i) => {
    const at = turn(99 - i)
    return group(`grp-late-${99 - i}`, [returned(`adm-late${String(99 - i).padStart(2, '0')}bb22cc`, `review-round-${99 - i}.md`, at, 9_000 + i)], { source: at })
  }),
  { total_groups: 13, omitted_groups: 5, omitted_group_items: 17, next_results_before: 'groups:before:grp-late-92' },
)

/** The older page, which holds #88 and a return of thirteen files whose
 *  first four only are on this page. */
export const olderPage: ResultPage = page([
  group('grp-88', [
    returned(GEN3[0], 'g3a-yellow-puck.png', T88),
    returned(GEN3[1], 'g3b-yellow-puck.png', T88),
    returned(GEN3[2], 'gen3-comparison.html', T88, 639_715),
    postRef('ent-p88compare01', T88, 88),
  ], { source: T88, total_items: 5, omitted_items: 1, next_items_after: 'items:grp-88:4' }),
  group('grp-80-wide', Array.from({ length: 4 }, (_, i) => returned(`adm-80f${i}11bb22cc`, `gen2-shot-${i + 1}.png`, T80, 120_000 + i)),
    { source: T80, total_items: 13, omitted_items: 9, next_items_after: 'items:grp-80-wide:4' }),
], { total_groups: 13, omitted_groups: 3, omitted_group_items: 4, next_results_before: 'groups:before:grp-61' })

/** #88's remaining item, as its continuation read returns it. */
export const group88Rest: ResultPage = page([
  group('grp-88', [purged('adm-88dead11bb22', 'gen3-raw-capture.png', T88)],
    { source: T88, total_items: 5, omitted_items: 0, next_items_after: null }),
], { total_groups: 13, omitted_groups: 0, omitted_group_items: 0 })

/** The nine remaining files of the thirteen-file return. */
export const wideRest: ResultPage = page([
  group('grp-80-wide', Array.from({ length: 9 }, (_, i) => returned(`adm-80f${i + 4}11bb22cc`, `gen2-shot-${i + 5}.png`, T80, 130_000 + i)),
    { source: T80, total_items: 13, omitted_items: 0, next_items_after: null }),
], { total_groups: 13, omitted_groups: 0, omitted_group_items: 0 })

/** A Work whose read found nothing: not an error, and not "no results". */
export const emptyPage: ResultPage = page([], { total_groups: 0 })

/** The refusal the server sends when paging cursors moved or are foreign. */
export const REFRESH = { kind: 'ResultsRefreshRequired', error: 'the results moved while you were reading', refresh_results: true }
