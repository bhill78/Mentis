/* WHAT A RECORDED RESULT POINTS AT, AND WHETHER IT CAN BE OPENED -- ONE
 * CONTRACT, used by the result chooser, by Needs you's references, and by the
 * one host operation that opens them (`opener.ts`).
 *
 * THE DEFECT THIS ANSWERS (navigation review adm-d9152e0643d7, B4): each
 * surface decided for itself what a reference was and how to open it, by
 * reading labels, file names and media types. So the same artifact opened in
 * the viewer from a post and as a download from the dock, a file named `.pdf`
 * reached the PDF program whatever the server had said the bytes were, and a
 * reference that could not be opened at all was found out only by pressing it.
 *
 * WHAT IT IS, AND WHAT IT IS NOT. A destination is EXACT IDENTITY plus the
 * record's own facts about it: which Admission, post, record, URL or commit;
 * where the bytes actually came from; on what basis this result is associated
 * with this Work; whether the Brain holds it now. It carries NO authority bit:
 * nothing here approves, promotes or permits anything, and `opens` is a route
 * the server said exists, never permission to take it (`fluid/inspect.py`
 * says the same of its own field).
 *
 * EVERY WORD IS THE SERVER'S OWN. `availability` is `fluid/inspect.py`'s set,
 * with an artifact descriptor's `held` read as its `ok`; a word this build does
 * not know degrades to `unreadable` AND KEEPS THE SERVER'S REASON, rather than
 * inventing a state. `opens` is inspection's own set.
 *
 * PURE. No React, no fetch, no DOM: facts in, a decision out. That is what
 * lets `tests/quiet2_result_targets_unit.ts` check the rules of this round --
 * openability, the URL policy, commit identity, launch and Brain identity --
 * without a browser. */
import type { HeldBytes, ViewerItem } from '../../quiet/media/view'
import type { ViewerSource } from '../viewer/types'

/* -- exact identity --------------------------------------------------------- */

/** A record identity as Mentis writes one, where a RECORD states it: an entry,
 *  a request or an Admission. Case and length are the canonical validator's
 *  (`mentis/decision_presentation.py` `reference`), not a stricter guess. */
export const isRefId = (id: string) => /^(?:ent|opr|adm)-[0-9a-fA-F]+$/.test(id)

/** An Admission as PROSE carries one, where there is no typed reference and a
 *  token in somebody's words is all there is (navigation review NB1): exactly
 *  twelve lowercase hex digits, and nothing else is treated as a file. */
export const isProseAdmission = (id: string) => /^adm-[0-9a-f]{12}$/.test(id)

/** A whole commit, as the record states one. Nothing shorter is a commit
 *  here: an abbreviation names no exact object. */
export const isCommitSha = (sha: string) => /^[0-9a-fA-F]{40}$/.test(sha)

const isAdmission = (id: string) => /^adm-/.test(id)

/** WHAT A RESULT POINTS AT. Exact identities only: no label is parsed, and no
 *  kind is inferred from a file name or a media type. */
export type ResultTarget =
  /** held bytes, by their Admission */
  | { kind: 'artifact'; ref: string }
  /** a post, by its conversation and its own id */
  | { kind: 'post'; conversation: string; post: string }
  /** a Brain record or a request, by its exact reference */
  | { kind: 'record'; ref: string }
  /** a URL THE RECORD STATES, external to Mentis (`externalHref` below) */
  | { kind: 'url'; href: string }
  /** a commit, by its full revision and the repository it is in */
  | { kind: 'commit'; sha: string; repository?: string | null; record?: string | null }

/** `fluid/inspect.py`'s availability, exactly. An artifact descriptor's `held`
 *  is this set's `ok`; a word from a later server degrades to `unreadable`. */
export type Availability =
  | 'ok' | 'missing' | 'deleted' | 'erased' | 'unreadable' | 'purged'
  | 'not-held' | 'held-but-missing' | 'held-but-corrupt'

/** Inspection's own `opens`: a route that exists, not permission to take it. */
export type Opens = 'post' | 'record' | 'conversation' | 'file' | null

const AVAILABILITY = new Set<string>(['ok', 'missing', 'deleted', 'erased', 'unreadable', 'purged', 'not-held', 'held-but-missing', 'held-but-corrupt'])
const OPENS = new Set<string>(['post', 'record', 'conversation', 'file'])

/** The server's word for how available something is, in this set. `held` (an
 *  artifact descriptor's word) is `ok`; anything this build does not know is
 *  `unreadable`, and the server's own reason is what says why. */
export const availabilityOf = (word: string | null | undefined): Availability => {
  const w = (word ?? '').trim().toLowerCase()
  if (w === 'held') return 'ok'
  return AVAILABILITY.has(w) ? (w as Availability) : 'unreadable'
}

/** The server's word for what a reference opens, in inspection's set. */
export const opensOf = (word: string | null | undefined): Opens =>
  word && OPENS.has(word) ? (word as Opens) : null

/* -- how a result came to be this Work's ------------------------------------ */

/** THREE SEPARATE FACTS, never merged into one claim (navigation review B2).
 *  A run RETURNED these bytes; a post HAS them attached; a claim WROTE this
 *  reference in its own `results`. The third establishes neither production
 *  nor reach, and on its own it never becomes an actionable deliverable. */
export type Basis = 'returned-by-run' | 'attached-to-turn' | 'authored-result-ref'

/** Whether the record's own facts make this an actionable Work deliverable:
 *  an authored claim alone does not (B2), independent returned or attached
 *  provenance does. */
export const actionable = (basis: readonly Basis[]): boolean =>
  basis.some((b) => b === 'returned-by-run' || b === 'attached-to-turn')

/** What a claim-only reference is honestly called. Never "produced by". */
export const REFERENCED_ONLY = 'Referenced by this claim. The record does not say this work produced it.'

/* -- one destination -------------------------------------------------------- */

/** ONE THING A READER CAN OPEN, with the record's own facts about it. */
export interface ResultDestination {
  /** the Work or request it belongs to, where it belongs to one */
  work?: string | null
  /** the result group (its producing Turn, or an unplaced return's act) */
  group?: string | null
  target: ResultTarget
  /** what a person reads it as; never its id */
  label: string
  /** WHERE THE CONTENT ACTUALLY CAME FROM, which is not where it was opened
   *  from: a post (with its conversation), or the Brain itself. Null where the
   *  record states no origin -- and none is invented for a URL or a commit. */
  source: ViewerSource | null
  basis: Basis[]
  /** the record's facts agree about this association */
  verified: boolean
  availability: Availability
  /** the server's own answer, read on that read: not a promise about later */
  available: boolean
  opens: Opens
  /** why it cannot be opened, or what is wrong, in the server's words */
  reason?: string | null
  /** held bytes, where a file is to be opened without a second read */
  file?: HeldBytes | null
  /** the bytes as the viewer reads them, where the caller already has them */
  item?: ViewerItem | null
}

/** WHETHER IT CAN BE OPENED AT ALL, and why not where it cannot.
 *
 *  `state === 'ok'` IS NOT THE CHECK (focused review M2.2): inspection answers
 *  `ok` with `opens: null` for an orphan post, a postless expectation and a
 *  run or activity act -- available, and still nothing to open. Both facts are
 *  asked, so those rows say what they are instead of offering a broken press.
 *
 *  A URL and a commit are not inspection routes and are expected to carry
 *  `opens: null`: their own discriminant answers for them. */
export function openable(d: ResultDestination): { can: boolean; why: string | null } {
  if (d.target.kind === 'url') return { can: true, why: null }
  if (d.target.kind === 'commit') return { can: true, why: null }
  if (!d.available || d.availability !== 'ok') return { can: false, why: d.reason ?? goneWords(d.availability) }
  if (d.opens === null) return { can: false, why: d.reason ?? 'The record holds it, and there is nothing here that opens it.' }
  if (d.target.kind === 'artifact' && d.opens !== 'file') return { can: false, why: d.reason ?? 'The record does not offer this as a file.' }
  return { can: true, why: null }
}

/** What is wrong, said as what it is. Never blank and never a guess. */
export function goneWords(a: Availability): string {
  switch (a) {
    case 'ok': return 'It can be read.'
    case 'missing': return 'This Brain does not hold it.'
    case 'deleted': return 'It was deleted.'
    case 'erased': return 'It was permanently deleted.'
    case 'purged': return 'Its contents were purged from this Brain.'
    case 'not-held': return 'Mentis does not hold its contents.'
    case 'held-but-missing': return 'The record holds it, and its bytes are not where they should be.'
    case 'held-but-corrupt': return 'The record holds it, and its bytes do not read as what was stored.'
    case 'unreadable': return 'It could not be read.'
  }
}

/** WHAT PRESSING IT DOES. The target's own discriminant decides, never the
 *  availability word and never the label: a URL and a commit invoke external
 *  and identity handling rather than a fabricated file route. */
export type ResultAction = 'file' | 'post' | 'record' | 'conversation' | 'external' | 'commit' | 'unavailable'

export function actionOf(d: ResultDestination): ResultAction {
  const t = d.target
  if (t.kind === 'url') return 'external'
  if (t.kind === 'commit') return 'commit'
  if (!openable(d).can) return 'unavailable'
  if (t.kind === 'artifact') return 'file'
  if (t.kind === 'post') return 'post'
  return d.opens === 'conversation' ? 'conversation' : 'record'
}

/** WHERE THE BYTES CAME FROM, for the viewer's own header: the post the record
 *  names, else the Brain this page serves. The Brain is not hardcoded where a
 *  post is known (B4: `fileFromDock` did exactly that), and no post is
 *  invented where the record names none.
 *
 *  THE KEY HERE IS THE GRAPH'S (`space/registry.ts` `spaceBrainKey`), because
 *  that is what a `ViewerSource` holds -- never the serving identity a result
 *  decision is made against (`results/serving.ts`; re-review
 *  adm-af5263a65134, F2). */
export function sourceOf(d: ResultDestination, spaceKey: string | null): ViewerSource | null {
  if (d.source) return d.source
  return spaceKey ? { kind: 'brain', brainKey: spaceKey } : null
}

/* -- URLs the record states ------------------------------------------------- */

/** THE ONE URL POLICY OF THIS OPENER (navigation review B2, P5). A result URL
 *  is opened only where the RECORD STATED IT as a URL, and only then:
 *
 *    - absolute `http:` or `https:`, with a host and no credentials in it;
 *    - not this page's own origin, so no API path and no local file is
 *      dressed up as an external result.
 *
 *  Everything else -- `file:`, `javascript:`, `data:`, `mailto:`, a relative
 *  path, a Windows path, a same-origin address -- is refused HERE. Generic
 *  prose links are not this policy's business: `prose.tsx`'s own `safeHref`
 *  is unchanged by this work.
 *
 *  `origin` is the page's own (`location.origin`); without it a same-origin
 *  address cannot be told apart and is refused. */
export function externalHref(href: string, origin: string | null): string | null {
  const raw = (href ?? '').trim()
  if (!raw || /[\u0000-\u001f\s]/.test(raw)) return null
  let u: URL
  try { u = new URL(raw) } catch { return null }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null
  if (!u.hostname) return null
  if (u.username || u.password) return null
  if (!origin) return null
  if (u.origin === origin) return null
  return u.toString()
}

/** How a recorded external link is opened: a new tab, on a press, and nothing
 *  else. No iframe, no prefetch, no availability probe (B2). */
export const EXTERNAL_LINK = { target: '_blank', rel: 'noreferrer noopener' } as const
export const EXTERNAL_WORDS = 'Opens outside Mentis, in a new tab.'

/* -- commits ---------------------------------------------------------------- */

/** A commit as the record states one: a whole revision and the repository it
 *  is in (`decision_presentation.py`'s `commit` reference: `repository` and a
 *  40-hex `sha`), and the record that states it, where one does. A shortened
 *  revision is not accepted, and no repository URL is invented. */
export type CommitTarget = Extract<ResultTarget, { kind: 'commit' }>

export function commitTarget(c: { sha?: unknown; repository?: unknown; record?: unknown }): CommitTarget | null {
  if (typeof c.sha !== 'string' || !isCommitSha(c.sha)) return null
  const repository = typeof c.repository === 'string' && c.repository.trim() ? c.repository.trim() : null
  const record = typeof c.record === 'string' && isRefId(c.record) ? c.record : null
  return { kind: 'commit', sha: c.sha.toLowerCase(), repository, record }
}

/** WHAT A COMMIT OFFERS HERE. Through the record that states it, where there
 *  is one; otherwise its exact identity as text, said plainly. Nothing fetches
 *  Git, and no commit browser is claimed to exist. */
export const NO_COMMIT_VIEWER = 'There is no commit viewer here. The revision and repository are exact, to use with Git.'

export function commitOpens(t: CommitTarget): { how: 'record'; ref: string } | { how: 'identity'; words: string } {
  return t.record ? { how: 'record', ref: t.record } : { how: 'identity', words: NO_COMMIT_VIEWER }
}

/* -- adapting the record's own typed references ----------------------------- */

/** One reference as the decision presentation states it (`validate_question`'s
 *  `reference`): a record identity, a commit, or a URL. Its canonical schema
 *  is the sibling's and is not changed here; this only reads it. */
export type StatedReference =
  | { kind: 'record'; id: string; label?: string | null }
  | { kind: 'commit'; repository: string; sha: string; label?: string | null }
  | { kind: 'url'; url: string; label?: string | null }

/** THE RECORD'S OWN REFERENCE AS A TARGET, or null where it states nothing
 *  this opener can take. An `adm-` identity is held bytes; `ent-`/`opr-` is a
 *  record; a commit and a URL keep their own arms. */
export function targetOfStated(r: StatedReference | null | undefined, origin: string | null): ResultTarget | null {
  if (!r || typeof r !== 'object') return null
  if (r.kind === 'record') {
    if (typeof r.id !== 'string' || !isRefId(r.id)) return null
    return isAdmission(r.id) ? { kind: 'artifact', ref: r.id } : { kind: 'record', ref: r.id }
  }
  if (r.kind === 'commit') return commitTarget(r)
  if (r.kind === 'url') {
    const href = typeof r.url === 'string' ? externalHref(r.url, origin) : null
    return href ? { kind: 'url', href } : null
  }
  return null
}

/* -- a reference the server already resolved -------------------------------- */

/** ONE REFERENCE AS `fluid/inspect.py` ANSWERS IT (Needs you's own `Ref`,
 *  `quiet2/needs/inspect.ts`), read structurally so that this contract does
 *  not reach into the decision adapter's module -- whose schema is its
 *  owner's, not this round's. */
export interface ResolvedRef {
  id: string
  type: string
  label?: string | null
  available: boolean
  state: string
  why?: string | null
  opens?: string | null
  relation?: string | null
  post?: string | null
  conversation?: string | null
  file?: HeldBytes | { state: string; name?: string | null; size?: number | null; claimed_media_type?: string | null } | null
}

/** THE SAME REFERENCE AS A DESTINATION, so that the dock, Needs you and the
 *  result chooser stop each deciding for themselves what a reference is and
 *  whether it opens (`GlobalDock.tsx`'s `can`/`open` did exactly that).
 *
 *  The server's `opens` chooses the route, and the reference's own id chooses
 *  the identity -- an `adm-` with `opens: 'file'` is held bytes; a post route
 *  needs the conversation the server named, and without it there is no post
 *  target to make rather than a guessed one. */
export function destinationOfRef(r: ResolvedRef, over: Partial<ResultDestination> = {}): ResultDestination {
  const opens = opensOf(r.opens)
  const availability = availabilityOf(r.state)
  const target: ResultTarget = opens === 'file' || (isRefId(r.id) && isAdmission(r.id))
    ? { kind: 'artifact', ref: r.id }
    : opens === 'post' && r.conversation && r.post
      ? { kind: 'post', conversation: r.conversation, post: r.post }
      : opens === 'conversation' && r.conversation
        ? { kind: 'record', ref: r.conversation }
        : { kind: 'record', ref: r.id }
  /* a post route the server named without a conversation opens nothing: it is
     said, not guessed at from whatever conversation is shown */
  const routeless = opens === 'post' && !(r.conversation && r.post)
  return {
    target,
    label: r.label || r.id,
    source: r.conversation && r.post ? { kind: 'post', conversation: r.conversation, post: r.post } : null,
    basis: [],
    verified: true,
    availability,
    available: !!r.available && availability === 'ok',
    opens: routeless ? null : opens,
    reason: r.why ?? null,
    file: (r.file && 'state' in r.file ? { ref: r.id, ...r.file } : null) as HeldBytes | null,
    ...over,
  }
}

/** The same identity, whatever it was reached through: used to tell one
 *  destination from another without comparing labels. */
export function targetKey(t: ResultTarget): string {
  switch (t.kind) {
    case 'artifact': return `artifact:${t.ref}`
    case 'post': return `post:${t.conversation}:${t.post}`
    case 'record': return `record:${t.ref}`
    case 'url': return `url:${t.href}`
    case 'commit': return `commit:${t.repository ?? ''}:${t.sha}`
  }
}
