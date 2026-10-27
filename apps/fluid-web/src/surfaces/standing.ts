import { post, read, type Id, type ProposedRead } from '../api'

/* ------------------------------------------------------------------------ *
 * THE STANDING ACTS, IN ONE PLACE.
 *
 * Establishing is the substrate's own vocabulary, and the route behind this
 * takes any entry: standing is a property of an entry, not of a topic. So
 * nothing here names a Kind, and nothing here decides what a Kind can do —
 * the Kind's own definition says that, and this only reads it.
 *
 * WHY THIS MODULE EXISTS. The conversation header already offered establish
 * over this route and the inspector now offers it too. Two copies of the route
 * and the attribution shape would be two places to get the owner's attribution
 * wrong.
 * ------------------------------------------------------------------------ */

/** Confer standing on an existing entry. Nothing is created and nothing is
 *  rewritten: the act is a link, and `because` rides on the link.
 *
 *  `by` is who the act is ATTRIBUTED TO — the owner. Whoever proposed the
 *  material stays its author; establishing it is somebody else's act. */
export const establish = (entry: Id, by: Id | null, because = 'accepted') =>
  post('/api/entries/' + entry + '/establish', { attributed_to: by, because })

/** Record a disagreement with an entry, saying why.
 *
 *  A DISPUTE CONFERS NOTHING AND REVOKES NOTHING. The route writes an ordinary
 *  note carrying `because` and a `disputes` link from it to the entry; material
 *  that stood still stands, and a proposal is still only proposed. */
export const dispute = (entry: Id, by: Id | null, because: string) =>
  post('/api/entries/' + entry + '/dispute', { attributed_to: by, because })

/** Replace an entry with a successor that already exists.
 *
 *  THE ONLY WAY MATERIAL CHANGES. An entry is immutable; a better one replaces
 *  it and the record keeps both and which came after. The route decides what
 *  may replace what — same Kind, standing, placed where the old one applied —
 *  and says why when it refuses; nothing here second-guesses it. */
export const supersede = (entry: Id, replacement: Id, by: Id | null, because = 'replaced') =>
  post('/api/entries/' + entry + '/supersede', { attributed_to: by, replacement, because })

/** Put an entry forward as a replacement for one or more others.
 *
 *  IT REPLACES NOTHING. The route writes one `proposes-to-supersede` link per
 *  predecessor and stops: nothing is established, nothing is ended, every
 *  predecessor goes on standing, and several competing proposals may name the
 *  same one. Hand `replacement` for material that already exists, or `body`
 *  for the words of a candidate to be written. */
export const proposeSupersession = (
  predecessor: Id,
  by: Id | null,
  opts: { replacement?: Id; body?: Record<string, string>; alsoReplaces?: Id[]; because?: string },
) =>
  post('/api/entries/' + predecessor + '/propose-supersession', {
    attributed_to: by,
    replacement: opts.replacement,
    body: opts.body,
    also_replaces: opts.alsoReplaces ?? [],
    because: opts.because ?? '',
  })

/** Approve a proposed successor. ONE ACT, and the route keeps it one.
 *
 *  The successor is established AND one `supersedes` link is written per
 *  predecessor, together or not at all. `alsoReplaces` names the rest; left
 *  out, the route replaces everything the proposal itself named, because that
 *  is what was put forward and what is being approved. */
export const establishReplacement = (
  predecessor: Id,
  replacement: Id,
  by: Id | null,
  because = 'the proposed replacement was accepted',
  alsoReplaces?: Id[],
  falsifier?: string,
) =>
  post<{ entry: Id; replacement: Id; answers_a_request?: boolean }>(
    '/api/entries/' + predecessor + '/establish-replacement',
    {
      attributed_to: by,
      replacement,
      because,
      ...(falsifier ? { falsifier } : {}),
      ...(alsoReplaces ? { also_replaces: alsoReplaces } : {}),
    },
  )

/** The shape `readProposal` needs of an entry read. Deliberately the few
 *  fields an act has to speak about, not the whole entry. */
interface ProposalRead {
  id: Id
  kind: string | null
  fields?: string[]
  body: Record<string, unknown>
  stands: boolean
  author_alias?: string | null
  established_by: Id[]
  superseded_by: Id[]
  standing_apt?: boolean | null
  proposed?: ProposedRead | null
}

/** One item, as an act needs to speak about it. `standing` is the word this
 *  interface is allowed to say, or null where the Kind has not declared that
 *  standing means anything. */
export interface ActableItem {
  entry: Id
  kind: string | null
  text: string
  stands: boolean
  author_alias?: string | null
  standing: string | null
}

/** A proposed successor and EVERYTHING approving it would end, read from the
 *  record before anything is said about it.
 *
 *  WHY IT IS A READ AND NOT A GUESS FROM WHAT IS ON SCREEN. A proposal may
 *  name several predecessors and the one a reader happens to be standing on
 *  is only one of them. A dialog that said "it ends this" while the act ended
 *  three would be describing itself falsely, and the owner would be confirming
 *  a sentence that was not true. So the successor's own read is asked for the
 *  rest, wherever the offer is made -- the register row, the inspector and the
 *  timeline all call this and none of them assembles its own answer. */
export async function readProposal(
  successor: Id,
): Promise<{ successor: ActableItem; ends: ActableItem[] }> {
  const s = await read<ProposalRead>('/api/entries/' + successor)
  const first = (s.fields ?? []).find(
    (f) => typeof s.body[f] === 'string' && String(s.body[f]).trim(),
  )
  return {
    successor: {
      entry: s.id,
      kind: s.kind,
      text: first ? String(s.body[first]) : 'nothing written in its fields',
      stands: s.stands,
      author_alias: s.author_alias ?? null,
      standing: standingWords(s),
    },
    ends: (s.proposed?.predecessors.items ?? []).map((x) => ({
      entry: x.entry,
      kind: x.kind,
      text: x.summary ?? 'nothing written in its fields',
      stands: x.stands,
      standing: x.state,
    })),
  }
}

/** What an entry read says about standing.
 *
 *  `standing_apt` is NOT a fact about this entry. It is the CURRENT Kind
 *  definition's answer to whether instances of that Kind participate in
 *  standing at all, and the server reads it from the current definition rather
 *  than from the version this entry pinned — `standing_apt_from` says so. The
 *  entry's own `fields` and `meaning` stay pinned to the version it was written
 *  against, and this never speaks for those. */
export interface StandingFacts {
  stands: boolean
  established_by: Id[]
  superseded_by: Id[]
  /** true | false | null, where null means UNKNOWN and never means false. */
  standing_apt?: boolean | null
}

/** Where an entry is, as governed material. FOUR ANSWERS, NEVER MERGED.
 *
 *  THE SAME CLASSIFICATION THE RECORD ALREADY COMPUTES, so the inspector and
 *  the conversation header cannot disagree. `governs()` sorts material the same
 *  four ways:
 *    stands     established, and nothing has superseded it
 *    ended      superseded AFTER it had been established — it used to hold
 *    replaced   superseded while nobody had ever established it. It never held,
 *               so it is not ended and not formerly standing; the supersession
 *               is the recorded answer to the proposal, and it is kept, visibly
 *               and unchanged, as what was proposed and then replaced
 *    candidate  written, and neither established nor answered by a successor
 *
 *  This is interaction semantics, not a rule of the substrate: the generic
 *  route still accepts an establishment of a replaced entry. The interface
 *  simply does not offer one, because the proposal has been answered. */
export type Standing = 'stands' | 'ended' | 'replaced' | 'candidate'

export const standingOf = (d: StandingFacts): Standing => {
  if (d.stands) return 'stands'
  if (d.superseded_by.length > 0)
    return d.established_by.length > 0 ? 'ended' : 'replaced'
  return 'candidate'
}

/** Is standing UNDECLARED for this entry's Kind — UNKNOWN, never false?
 *
 *  True when the entry HAS a Kind and that Kind's current definition carries
 *  no `standing_apt`. Then nobody has said whether standing means anything for
 *  it, so no standing word — stands, does not stand, proposed, superseded,
 *  replaced — may be said of it: each one answers the question the record has
 *  not answered. Its recorded establish and supersede links are still facts
 *  and are still shown as such.
 *
 *  `false` is NOT undeclared: that Kind has said standing does not apply, and
 *  what is shown for it is unchanged. An entry with no Kind at all (a
 *  definition, a link) is not this case either and is also unchanged. */
export const standingUndeclared = (d: StandingFacts & { kind?: string | null }) =>
  Boolean(d.kind) && (d.standing_apt === null || d.standing_apt === undefined)

/** Is this a candidate — written, and standing neither conferred nor answered? */
export const isCandidate = (d: StandingFacts) => standingOf(d) === 'candidate'

/** May the owner be offered Establish for this entry?
 *
 *  THREE ANSWERS, AND ONLY ONE OF THEM OFFERS ANYTHING. `standing_apt === true`
 *  and a candidate: offered — and a candidate only, so material that was
 *  replaced before anybody established it is not offered either. `false`: the Kind does not participate in standing,
 *  so there is nothing to offer. `null`/absent: UNKNOWN — nobody has established
 *  whether standing means anything for this Kind, and guessing either way would
 *  answer a question the record has not answered. UNKNOWN offers nothing and is
 *  not treated as false.
 *
 *  `by` is required because an establishment has to be attributed to somebody. */
export const mayEstablish = (d: StandingFacts | null | undefined, by: Id | null) => {
  if (!d || !by) return false
  if (d.standing_apt !== true) return false
  return isCandidate(d)
}

/** Does this Kind take part in standing — the gate the ADJUDICATING acts
 *  share. KNOWN TRUE ONLY: false offers nothing, and UNKNOWN offers nothing
 *  without being read as false.
 *
 *  IT IS NOT A GATE ON DISPUTE. See `mayDispute`. */
const participates = (d: StandingFacts) => d.standing_apt === true

/** May the owner be offered Dispute?
 *
 *  ON ANYTHING STILL LIVE, AND GATED BY NO KIND. A dispute records a challenge
 *  and what is wrong with the material, and erases, revokes, rewrites and
 *  supersedes nothing — so there is no state it could put anything into that
 *  the Kind would have had to agree to first. `finding` and `note` are
 *  declared ungated supporting material (`standing_apt: false`): nobody
 *  adjudicates them, and they are disputable exactly like everything else,
 *  because disagreeing with a note is disagreeing with a note. The server
 *  gates it by nothing either; it refuses only an EMPTY challenge, since a
 *  challenge carries its evidence and an empty one records that somebody
 *  objected while losing the only part worth keeping.
 *
 *  WHAT IS STILL GATED IS THE STATE, NOT THE KIND. Material that has ended or
 *  was replaced is not offered: the record already answered those, and an
 *  objection to history is not an act on anything that holds. */
export const mayDispute = (d: StandingFacts | null | undefined, by: Id | null) => {
  if (!d || !by) return false
  const s = standingOf(d)
  return s === 'stands' || s === 'candidate'
}

/** May the owner be offered Supersede?
 *
 *  THE SAME GATE AS ESTABLISH, DELIBERATELY, because the two are the ends of
 *  one axis: establishing confers standing, superseding ends it or answers the
 *  proposal. Ungating only the withdrawal would let this interface end
 *  material it would never have offered to establish.
 *
 *  AND BECAUSE THE ACT CANNOT BE DESCRIBED WITHOUT STANDING WORDS. Everything
 *  said about it before the click -- `supersedeEffect` -- and the state word
 *  said after it are sentences about standing: "it stops standing", "it will
 *  never have stood". For a Kind whose current definition says standing does
 *  not apply, or has not said, `standingWords` already refuses to say any of
 *  them, so offering the act would promise an outcome this interface could not
 *  then report. Ungated supporting material is challenged, not replaced: a
 *  dispute on it explicitly does not supersede it.
 *
 *  The two live states only. Superseding material that stands ENDS it;
 *  superseding a proposal ANSWERS it, and it becomes `replaced` — never held,
 *  kept as it was, and no longer offered Establish. */
export const maySupersede = (d: StandingFacts | null | undefined, by: Id | null) => {
  if (!d || !by || !participates(d)) return false
  const s = standingOf(d)
  return s === 'stands' || s === 'candidate'
}

/** Record that a dispute was considered and the material held.
 *
 *  THE OPPOSING ACT ON THE SAME AXIS, not a third link and not a supersession
 *  of the challenge: the route writes a `supports` link naming the `disputes`
 *  link it answers, and leaves that link exactly where it was. Both facts stay
 *  true — it was disputed AND it stands — because the argument is the part
 *  worth keeping.
 *
 *  A REASON IS REQUIRED, exactly as it is for the challenge. A free dismissal
 *  is not an answer to an argument, and the route refuses one. */
export const setAside = (entry: Id, dispute: Id, by: Id | null, because: string) =>
  post('/api/entries/' + entry + '/set-aside', { attributed_to: by, dispute, because })

/** What a revision reports back. ONE REVISION MAY HAVE REPLACED SEVERAL
 *  PREDECESSORS, so each of these is plural exactly where the act was.
 *
 *  `predecessors` names every proposal the revision replaced, the one in the
 *  path first; `links` is the `supersedes` link written for each of them, so
 *  walking back from ANY predecessor finds the successor; `replaced` is what
 *  the record now says about each of them; and `placed_at` is the UNION of
 *  their placements, because everywhere the replaced material applied is
 *  somewhere the replacement has to apply, or ending it would leave that scope
 *  governed by nothing. */
export interface ReviseOutcome extends ActOutcome {
  entry: Id
  revision: Id
  kind: string | null
  predecessors: Id[]
  /** predecessor → the `supersedes` link recorded for it */
  links: Record<Id, Id>
  /** predecessor → what the record says about its standing after the act */
  replaced: Record<Id, unknown>
  placed_at: Id[]
}

/** Revise a proposal and establish the revision, in one act.
 *
 *  NOT AN EDIT. The proposal is kept exactly as it was written and was never
 *  established; a new entry of the same Kind carries the revised words, the
 *  owner's act establishes it, and the record says it replaced what was
 *  proposed. Placement is inherited, because placement is what makes material
 *  apply.
 *
 *  `body` is the revised material in the fields its Kind declares — which
 *  nothing here enumerates. The caller passes back the fields the item itself
 *  reported, and the Kind's own refusal comes back in the Kind's own words.
 *
 *  `also` NAMES THE OTHER PROPOSALS THIS ONE REVISION REPLACES, and it is what
 *  makes "replace both with one" a single act. The owner's decision is one
 *  decision — these several proposals should be this one set of words — and
 *  performing it as two acts would record two, leave a moment in which one
 *  predecessor was replaced and its sibling was not, and make the sentence the
 *  dialog showed beforehand untrue. The route writes one `supersedes` link per
 *  predecessor, so each of them records what replaced it; it inherits the
 *  placements of all of them; and it applies the supersede path's own refusals
 *  to every predecessor inside one transaction, where a refusal rolls the whole
 *  thing back and names the predecessor it is about. Empty is the
 *  single-predecessor shape, unchanged, so nothing is sent when nothing is
 *  named. */
export const revise = (
  entry: Id,
  body: Record<string, unknown>,
  by: Id | null,
  because = 'revised and established',
  also: Id[] = [],
) =>
  post<ReviseOutcome>('/api/entries/' + entry + '/revise', {
    attributed_to: by,
    body,
    because,
    ...(also.length > 0 ? { also_replaces: also } : {}),
  })

/** What an act reports about the request it answered, where it answered one.
 *
 *  EVERY ACT ASKS. An owner who was asked to decide something and then went
 *  and did it has answered it, and being asked again would be the record
 *  failing to notice what they just did. `say` is the server's own sentence
 *  and is shown as it stands, never rephrased here. */
export interface ActOutcome {
  answers_a_request?: boolean
  say?: string
  answers?: { expectation: Id; of: Id | null; requested_by: Id | null; turn: Id | null }[]
}

/** What superseding will do to THIS entry, said before the click. */
export const supersedeEffect = (d: StandingFacts): string =>
  standingOf(d) === 'stands'
    ? 'ends this: it stops standing, and the successor holds in its place'
    : 'answers this proposal with its successor: it will never have stood, and stays visible as replaced before establishment'

/** Where an entry stands, in a few words, for a place that only mentions it.
 *
 *  null WHERE STANDING DOES NOT APPLY OR IS NOT KNOWN TO. A Kind that does not
 *  participate says nothing about standing, and neither does one whose answer
 *  is UNKNOWN — "proposed" would be a claim about a Kind nobody has judged.
 *  Where it does participate, a proposal is never allowed to read as held. */
export const standingWords = (d: StandingFacts | null | undefined): string | null => {
  if (!d || d.standing_apt !== true) return null
  switch (standingOf(d)) {
    case 'stands':
      return 'stands'
    case 'ended':
      return 'superseded'
    case 'replaced':
      return 'replaced before establishment'
    default:
      return 'proposed · reaches nobody unless established'
  }
}
