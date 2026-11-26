/* THE PERSISTENT COMPOSER, in the card's footer slot.
 *
 * The approved hybrid card can be written in from wherever the owner is: the
 * bar is present on all six tabs and in the search overlay, and absent only in
 * settings (the frame decides that, by not rendering this slot there). It is
 * the real `fluid/Composer` through the `miniAsking()` adapter, so addressing,
 * the split send, Work permissions and the five keyboard conventions are the
 * app's own and are not re-implemented here.
 *
 * What this file owns: where the composer sits, the discussion reference chip,
 * the "What Mentis reads" choice, and what happens when a message is sent --
 * the real request, the return route, and the move to the Conversation.
 *
 * Nothing here is a second posting system: every write goes through the same
 * store and the same audited request door. NOTHING THIS FILE KNOWS IS WRITTEN
 * AS THE AUTHOR'S WORDS: what the message is about travels as the managed
 * selector (`contract.ts`, revised contract adm-c5c73679ac1e §§2-5), by exact
 * identity, and the words recorded are the words that were typed. */

import { useEffect, useLayoutEffect, useMemo, useRef, useSyncExternalStore } from 'react'
import type { ReactNode, RefObject } from 'react'
import Composer from '../../fluid/Composer'
import { useBrainBound } from '../../brainBinding'
import {
  MANAGED_REFUSAL, SELECTOR_FIELD, digestOf, emptySelectorV1, isDigestHex, validateExplicitSelector,
  type CanonicalValue, type MagnetCarried, type MagnetContext, type MagnetResource,
  type MagnetSelectorReference, type MagnetSelectorV1, type ManagedRefusalReason, type Sha256Hex,
} from './contract'
import { miniAsking } from './asking'
import {
  NO_OWN_CONVERSATION, attachContext, miniAttempt, miniConversationOf, removeContext, retireContext,
} from './conversation'
import { linkHost, rowHeadline, rowLink } from './links'
import { place, remember, route, writePlace } from './places'
import { perspectivesOf, perspectiveRequest } from './perspectives'
import './conversation.css'
import './composer.css'

/** A scroll past the end of the Conversation: the frame's one scroll container
 *  clamps it, which is how "pinned to the bottom" stays true once a message
 *  has been added to the page. */
export const PIN_TO_BOTTOM = 1e7

/** The chip's words. The reference is the chip: the label is only what the
 *  owner could already see in the view they attached it from. */
export const contextWords = (c: MagnetContext): string => `${c.label || c.ref}`

/** WHAT THE CHIP IS, IN ORDINARY WORDS (owner §2). The kinds are the record's
 *  vocabulary; what the reader needs is which thing this is, so the chip says
 *  "question" rather than "perspective" and "file" rather than "admission",
 *  and the identifier itself is not drawn in the sentence. */
export const CONTEXT_WORDS: Record<MagnetContext['kind'], string> = {
  post: 'post',
  file: 'file',
  image: 'picture',
  attachment: 'file',
  perspective: 'question',
  batch: 'collected information',
}

/* -- WHAT THIS MESSAGE IS ABOUT, AS EXACT IDENTITY ------------------------- *
 * The chip used to be written into the post as a sentence naming the record,
 * which is how an ordinary question came back as prose the owner never
 * typed (owner §5). It now travels as the managed selector: the saved
 * question's own version, or a selected object by ref, version and digest. A
 * selection the card cannot state EXACTLY is not sent at all -- not guessed,
 * not substituted and not turned back into words. */

/** The definition the configuration digest covers: the validated durable
 *  definition without the nonauthoritative own-Conversation mirror
 *  (`CONFIGURATION_DIGEST_EXCLUDES`; the door reads the same body). */
export const definitionBody = (config: unknown): CanonicalValue => {
  const c = (config && typeof config === 'object' && !Array.isArray(config) ? config : {}) as Record<string, unknown>
  const out: Record<string, unknown> = {}
  for (const k of Object.keys(c)) if (k !== 'conversation') out[k] = c[k]
  return out as CanonicalValue
}

export const configurationDigest = (config: unknown): Promise<Sha256Hex> => digestOf(definitionBody(config))

/** WHY A CHIP CANNOT BE SENT, when it cannot. Each says what the owner may do
 *  about it, and each keeps the words, the key and the chip exactly as they
 *  are: nothing here discards a draft to get past a refusal. */
export const RETAINED_NOT_SENDABLE = 'Collected information cannot be sent with a message yet: answering from the collection waits on configured-source access being enforced. Remove it to send this message, or read it in the collection.'
export const POST_NOT_SENDABLE = 'This record cannot be attached to a message from here yet, because the card has no exact version for it. Remove it to send this message.'
export const FILE_NOT_SENDABLE = 'This file cannot be attached to a message from here yet, because the card has no exact version for it. Remove it to send this message.'
export const DROPPED_REF_NOT_SENDABLE = 'A reference dropped into this message cannot be sent with it yet. Remove it, and refer to it in your words instead.'
export const QUESTION_CHANGED = 'The saved question changed while this message was being sent, so nothing was sent. Read it again and send your message.'
export const RECORD_CHANGED = 'The attached record is no longer the version this message was about, so nothing was sent. Attach it again and send your message.'

export type Selected<T> = { ok: true; value: T } | { ok: false; why: string }

/* -- THE VERSION THE CHIP STANDS FOR -------------------------------------- *
 * The chip used to carry an identifier alone, so the version it was sent with
 * was whatever the record held at the press: a question revised while the
 * owner was writing went out in place of the one they had read, and nothing
 * said so. What a chip stands for is now written on it when it is attached and
 * kept with it through a remount and a reload (`MagnetContext.version/digest`,
 * `workingState.ts`), and a send compares it against a FRESH durable read:
 * equal, it goes; different, deleted or unreadable, it refuses with words the
 * owner can act on. Nothing is rebound, substituted or recomputed. */

/** The exact version a chip was attached at. `version` is the record's own
 *  version identity -- the saved question's artifact, or null for an immutable
 *  artifact -- and `digest` is that version's recorded digest. */
export interface AttachedVersion { version: string | null; digest: Sha256Hex }

/** What this chip says it stands for, or null where it says nothing (attached
 *  by a view that states no version, or restored from a release that kept
 *  none). A digest is what makes a stamp a stamp: anything else is not one. */
export function attachedVersion(c: MagnetContext | null | undefined): AttachedVersion | null {
  if (!c || !isDigestHex(c.digest)) return null
  return { version: c.version === null || typeof c.version === 'string' ? c.version ?? null : null, digest: c.digest }
}

/** The same chip, saying which version it stands for. */
export const stamped = (c: MagnetContext, at: AttachedVersion | null): MagnetContext =>
  at ? { ...c, version: at.version, digest: at.digest } : c

/** THE VERSION A ROW SHOWS, for a chip being attached from it: the saved
 *  question's own artifact, or the held record's recorded digest. Null where
 *  the card has no exact version for that record -- it is then attachable
 *  deliberately and says at the press why it cannot be sent, exactly as before. */
export function versionOfRow(
  rows: readonly { perspective: string; question: { ref: string; digest: string } | null }[],
  perspective: string,
): AttachedVersion | null {
  const question = rows.find((p) => p.perspective === perspective)?.question
  return question && isDigestHex(question.digest) ? { version: question.ref, digest: question.digest } : null
}
export function versionOfRecord(
  rows: readonly { id: string; value?: unknown; reference?: unknown }[],
  ref: string,
): AttachedVersion | null {
  const row = rows.find((r) => r.id === ref)
  const served = collectedIdentity(row)
  if (served) return { version: served.version, digest: served.digest }
  const value = (row?.value ?? {}) as Record<string, unknown>
  return /^adm-/.test(ref) && isDigestHex(value.digest) ? { version: null, digest: value.digest as Sha256Hex } : null
}

/** WHAT A COLLECTED ROW CAN BE REFERRED TO BY, as the collection read served
 *  it: the row's captured version -- the recorded batch it belongs to and its
 *  own recorded digest (`mentis/magnet/collection.py`, contract §3). This is
 *  the one thing that makes a supporting record something a message can be
 *  about: the card states the identity the server gave it and nothing else, so
 *  no digest is ever computed here from captured text, and a row served no
 *  identity stays unsendable and says why at the press.
 *
 *  It is identity, not reach: what an agent may actually read of a collected
 *  record is still the door's decision, and the retained collection is still
 *  not answer evidence. */
export function collectedIdentity(row: { id: string; reference?: unknown } | undefined | null):
  MagnetSelectorReference | null {
  if (!row) return null
  const r = row.reference as Record<string, unknown> | undefined
  if (!r || r.kind !== 'collected_item' || r.ref !== row.id) return null
  if (typeof r.version !== 'string' || !r.version || !isDigestHex(r.digest)) return null
  return { kind: 'collected_item', ref: row.id, version: r.version, digest: r.digest }
}

/** ONE ATTACHED OBJECT, by exact identity, or why it is not sendable.
 *
 *  The digest is the record's own, read from the row the card is showing --
 *  never computed from captured text, and never left out so the door can
 *  "work it out". An artifact is immutable, so its version is null; anything
 *  whose exact version the card does not hold is refused here, where the owner
 *  can still act on it, rather than at the door. */
export function selectedReference(
  rows: readonly { kind?: string; id: string; version?: string; value?: unknown; reference?: unknown }[],
  c: MagnetContext,
): Selected<MagnetSelectorReference> {
  if (c.kind === 'batch') return { ok: false, why: RETAINED_NOT_SENDABLE }
  const row = rows.find((r) => r.id === c.ref)
  const value = (row?.value && typeof row.value === 'object' ? row.value : {}) as Record<string, unknown>
  /* A COLLECTED RECORD, AT THE VERSION IT WAS CAPTURED AT. Whichever kind of
     thing it is -- a collected post or a collected file -- the identity is the
     row's own, served by the collection read and checked again at the door
     against this Magnet's recorded batch. The chip must still stand for that
     exact version: a row that has changed since is the refusal below, never a
     quietly different record. */
  const served = collectedIdentity(row)
  if (served) {
    const at = attachedVersion(c)
    if (at && (at.version !== served.version || at.digest !== served.digest)) {
      return { ok: false, why: RECORD_CHANGED }
    }
    return { ok: true, value: served }
  }
  if (c.kind === 'post') return { ok: false, why: POST_NOT_SENDABLE }
  const digest = value.digest
  if (!/^adm-/.test(c.ref) || !isDigestHex(digest)) return { ok: false, why: FILE_NOT_SENDABLE }
  /* THE VERSION THE CHIP WAS ATTACHED AT, or nothing goes. A held record whose
     recorded digest is not the one this chip stands for is a different version
     of that record, and the message was about the one the owner was reading;
     a record no longer held at all has already refused above. */
  const held = attachedVersion(c)
  if (held && (held.version !== null || held.digest !== digest)) return { ok: false, why: RECORD_CHANGED }
  return { ok: true, value: { kind: 'artifact', ref: c.ref, version: null, digest } }
}

/** THE SAVED QUESTION THIS MESSAGE IS ABOUT, by its own version. The exact
 *  artifact the Perspective's current question IS -- read fresh from the
 *  record at the press -- so a question revised since the chip appeared is a
 *  refusal and never a quietly different question.
 *
 *  `held` is the version the chip itself stands for. Where the chip carries
 *  one, the fresh read must BE that version: it is the version the owner read
 *  and attached, and a later revision is a different question however it
 *  arrived -- revised under the composer, revised while the card was closed,
 *  or revised between a reload and this press. Where it carries none (a chip
 *  attached by a view that stated no version), the fresh read's own
 *  consistency is all there is, and that is what travels. */
export function selectedQuestion(
  ordinary: { perspective: string; revision: string } | null,
  rows: readonly { perspective: string; question: { ref: string; digest: string } | null }[],
  chip: string,
  held: AttachedVersion | null = null,
): Selected<MagnetSelectorV1['perspective']> {
  if (!ordinary || ordinary.perspective !== chip) return { ok: false, why: QUESTION_CHANGED }
  const row = rows.find((p) => p.perspective === chip)
  const question = row?.question
  if (!question || question.ref !== ordinary.revision || !isDigestHex(question.digest)) {
    return { ok: false, why: QUESTION_CHANGED }
  }
  if (held && (held.version !== question.ref || held.digest !== question.digest)) {
    return { ok: false, why: QUESTION_CHANGED }
  }
  return { ok: true, value: { id: chip, question_ref: question.ref, question_digest: question.digest } }
}

/** WHAT THE OWNER IS TOLD when the door refuses a managed send, in words that
 *  say what to do about it (contract §6: the reason is the door's, the sentence
 *  is this composer's). The draft, its key and its chip are kept in every one
 *  of these cases, so nothing the owner wrote is lost to a refusal. */
export const MANAGED_REFUSAL_WORDS: Record<ManagedRefusalReason, string> = {
  'authentication': 'Nothing was sent: this page is not signed in to the Brain the server serves.',
  'authority': 'Nothing was sent: this message is not yours to send here.',
  'request-door-required': 'Nothing was sent: this card sent the message the wrong way. Your words are kept; send them again.',
  'selector-schema': 'Nothing was sent: what this message says it is about could not be read. Remove the attached reference and send again.',
  'selector-too-large': 'Nothing was sent: too much was attached to this message. Remove a reference and send again.',
  'too-many-references': 'Nothing was sent: too many references are attached. Remove one and send again.',
  'duplicate-selection': 'Nothing was sent: the same reference is attached twice. Remove one and send again.',
  'invalid-unicode': 'Nothing was sent: your message contains a character that cannot be recorded. Edit it and send again.',
  'identifier-too-long': 'Nothing was sent: an attached reference could not be read. Remove it and send again.',
  'context-too-large': 'Nothing was sent: what was attached is too large to send with a message. Remove it and send again.',
  'text-parts-disagree': 'Nothing was sent: your words and what was recorded with them did not agree, so nothing was recorded. Send them again.',
  'blank-without-content': 'Write something to send, or attach a file.',
  'selection-unavailable': 'Nothing was sent: the attached reference is no longer available. Remove it and send again.',
  'managed-data-missing': 'Nothing was sent: this message is missing what it needs to be recorded here. Your words are kept; send them again.',
  'retained-execution-intent': RETAINED_NOT_SENDABLE,
  'stale-configuration': 'Nothing was sent: this Magnet’s configuration changed while you were writing. Send your message again.',
  'brain-mismatch': 'Nothing was recorded: this server now serves another Brain than this card was opened on. Reload for the Brain it serves; your words are kept.',
  'authored-version-edited': 'Nothing was sent: this message was edited after it was prepared. Send it again as a new message; the earlier one is unchanged.',
  'replay-intent-changed': 'Nothing was sent: an unresolved send under this key carried something else. Resolve that one, then send this.',
  'conflicting-association': 'Nothing was sent: this Conversation is claimed by more than one Magnet. Nothing was changed.',
}

/** The door's own reason, where it says one, as words the owner can act on. */
export const refusalWords = (reason: unknown): string | null =>
  typeof reason === 'string' && reason in MANAGED_REFUSAL
    ? MANAGED_REFUSAL_WORDS[reason as ManagedRefusalReason] : null

/** What building the selector needs: the card's own state, and the Perspective
 *  store's FRESH durable read (never its rendered state). */
export interface SelectionSeam {
  resource: MagnetResource
  inquiries: {
    ordinaryContext(): Promise<{ perspective: string; revision: string } | null>
    snapshot(): { rows: readonly { perspective: string; question: { ref: string; digest: string } | null }[] }
  }
}

/** WHAT THIS MESSAGE IS ABOUT, as the explicit selector, for EVERY action.
 *
 *  A recorded note carries one as much as a question does: the door resolves
 *  the route itself and validates the words against the parts either way, and
 *  "nothing is selected" has to be said explicitly -- the full v1 object with
 *  a null question and no references -- because an absent selector is a
 *  different submitted identity, and because nothing may be inferred on send.
 *
 *  IT CARRIES ONLY WHAT IS ACTUALLY SELECTED: the chip the owner can see. No
 *  chip -- never attached, or taken off -- is the empty selection, so a
 *  Perspective the owner removed reaches nothing at all. A selection the card
 *  cannot state exactly throws the owner's own sentence, which the composer
 *  shows while keeping the words, the key and the chip.
 *
 *  The action is deliberately not read: there is no branch here for a note, a
 *  question or an addressed request, so none of them can carry less. */
export async function managedSelector(seam: SelectionSeam, post: Record<string, unknown>): Promise<MagnetSelectorV1> {
  const { resource, inquiries } = seam
  const dropped = (post as { references?: unknown[] }).references
  if (Array.isArray(dropped) && dropped.length) throw new Error(DROPPED_REF_NOT_SENDABLE)
  const now = resource.snapshot()
  const selector = emptySelectorV1(await configurationDigest(resource.saved.config))
  const chip = now.context
  if (chip?.kind === 'perspective') {
    const question = selectedQuestion(await inquiries.ordinaryContext(), inquiries.snapshot().rows, chip.ref,
      attachedVersion(chip))
    if (!question.ok) throw new Error(question.why)
    selector.perspective = question.value
  } else if (chip) {
    const reference = selectedReference(now.results, chip)
    if (!reference.ok) throw new Error(reference.why)
    selector.references = [reference.value]
  }
  /* Checked here against the published schema and bounds before anything is
     sent, so a selection this card cannot state exactly is a refusal the owner
     can act on rather than one that comes back from the door. */
  const checked = validateExplicitSelector(selector)
  if (!checked.ok) throw new Error(MANAGED_REFUSAL_WORDS[checked.reason])
  return checked.selector
}

/** THE CANDIDATE, from where the owner actually is. The inspected item of the
 *  current place, else the selected Perspective when the Perspectives view (or
 *  a Perspectives search result) is what is open. Nothing else volunteers one,
 *  and a candidate is never content -- it is the reference the view is showing.
 *
 *  AUTOMATIC ATTACHMENT OFFERS ONLY WHAT CAN ACTUALLY BE SENT. A reference the
 *  card cannot state by exact identity is refused at the press, so attaching
 *  one by itself -- because the owner happened to be reading it when they
 *  started typing -- would put the composer in a state Send cannot leave. The
 *  owner may still attach such a record deliberately ("Discuss this record"),
 *  and is then told exactly why it cannot go with a message. */
export function contextCandidate(resource: MagnetResource,
  selected?: { perspective: string; name?: string | null } | null): MagnetContext | null {
  const s = resource.snapshot()
  const here = place(s)
  if (here.inspected) {
    const ref = here.inspected
    const row = s.results.find((r) => r.id === ref)
    const kind: MagnetContext['kind'] = row?.kind === 'post' ? 'post'
      : row?.kind === 'image' ? 'image'
      : /^adm-/.test(ref) ? 'file' : 'post'
    const value = row?.value as { title?: unknown } | undefined
    const title = typeof value?.title === 'string' && value.title ? value.title : ''
    // A collected web row leads with its own headline and site, read back out
    // of its verified bytes, rather than the held-file key underneath.
    const headline = row ? rowHeadline(row) : null
    const site = headline ? linkHost(rowLink(row!)) : null
    const label = headline ? `${headline}${site ? ` · ${site}` : ''}` : title || ref
    /* Attached AT the version the view is showing: the chip stands for that
       row, not for whatever the record holds when Send is pressed. */
    const candidate: MagnetContext = stamped({ ref, kind, label }, versionOfRecord(s.results, ref))
    return selectedReference(s.results, candidate).ok ? candidate : null
  }
  const onPerspectives = s.overlay === null ? s.tab === 'Perspectives' : s.searchTarget?.kind === 'Perspectives'
  const lens = selected?.perspective ?? s.lens
  if (onPerspectives && lens) return { ref: lens, kind: 'perspective', label: selected?.name || lens }
  return null
}

/** WHAT A RECORDED MESSAGE DOES TO THE CARD, as one act so it can be checked
 *  without a browser. Sending from anywhere but the Conversation saves the way
 *  back first and then goes to the Conversation; sending from the Conversation
 *  stays there and saves nothing (there is nowhere to return to). The message
 *  is the newest, so the Conversation is pinned to its bottom. The attached
 *  reference went with those words, so it is let go here, and suppression with
 *  it. Nothing here touches the draft: that is the store's, settled with the
 *  attempt even when the card that sent it is gone.
 *
 *  `carried` is what that send took with it, noted under its key when it went
 *  out (`carryContext`). This act may run long after the press -- the answer
 *  can land while the footer is unmounted, and then it is this bar's first act
 *  on mounting -- so the way back and the reference to let go are read from
 *  there and not from where the card is now. Without one (a direct call in a
 *  check) it behaves as before, from the card's current place. */
export function afterSent(resource: MagnetResource, carried: MagnetCarried | null = null): void {
  retireContext(resource, carried)
  if (!carried) remember(resource)
  const from = carried?.from ?? route(resource.snapshot())
  if (from.tab !== 'Conversation' || from.overlay) {
    resource.update({ returnRoute: from, tab: 'Conversation', overlay: null, searchTarget: null })
  }
  writePlace(resource, 'Conversation', { scroll: PIN_TO_BOTTOM, inspected: null, inspectScroll: 0 })
}

export interface ComposerBarProps {
  resource: MagnetResource
  canWrite: boolean
  /** Why not, when the reason is more exact than "not here": the host knows
   *  which operation it asked about (`capabilities.ts`). */
  cannotWriteBecause?: string
}

export default function ComposerBar({ resource, canWrite, cannotWriteBecause }: ComposerBarProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const bound = useBrainBound()
  const inquiries = useMemo(() => perspectivesOf(resource), [resource])
  const lens = useSyncExternalStore(inquiries.subscribe, inquiries.snapshot, inquiries.snapshot)
  const { at, store } = miniConversationOf(resource, canWrite, bound)
  const mini = useSyncExternalStore(store.subscribe, store.snapshot, store.snapshot)
  /* One adapter per store: the Composer's place key must not change between
     renders, or the draft it is holding would be a different draft. */
  const ask = useMemo(() => miniAsking(resource, store), [resource, store])
  const box = useRef<HTMLDivElement>(null)
  const typed = useRef<string>(mini.draft.trim())

  /* A target with no words is useful only while the owner is visibly acting
     on it. On a restored footer it is stale, so clear it before paint. A target
     accompanied by a non-empty draft remains intact across every remount. */
  useLayoutEffect(() => {
    if (mini.replyTo && !mini.draft.trim()) store.replyTo(null)
  }, [store]) // restore/open boundary, deliberately not every keystroke

  /* The send's own hooks, installed by the one component that sends: the
     frozen-question check, and WHAT THIS MESSAGE IS ABOUT as exact identity. */
  at.canWrite = canWrite
  /* WHAT WOULD MAKE AN UNRESOLVED SEND A DIFFERENT SEND: the saved question
     and its version, and the reference attached to it -- including the owner
     having taken one off. Changing any of those under an unresolved attempt is
     a different message, and the store refuses to resolve the old key with it. */
  at.contextKey = () => {
    const current = inquiries.snapshot()
    const now = resource.snapshot()
    /* THE VERSION THIS MESSAGE IS ABOUT, as the chip says it -- not whatever
       the record holds at this moment. A question revised under an unresolved
       send does not make the owner's own message a different one: its frozen
       request is still theirs to retry, and a press that would send the newer
       version is refused by `managedSelector`, in those words. */
    const held = attachedVersion(now.context)
    return `${current.selected ?? ''}:${held?.version ?? ''}:${held?.digest ?? ''}:${now.context?.ref ?? ''}:${now.contextSuppressed ? 'off' : 'on'}`
  }
  /* EVERY ACTION GOES THROUGH THE SAME HOOK, with no branch on which it is:
     `managedSelector` is what decides, and it reads the chip, not the action. */
  at.beforeRequest = async (post, op) => {
    const previous = miniAttempt(resource)
    if (previous?.perspective && ['in-flight', 'uncertain', 'malformed'].includes(previous.state)) throw new Error('Resolve the original frozen question’s request before sending a different question.')
    const selector = await managedSelector({ resource, inquiries }, post)
    /* THE FROZEN ASK, carried through unchanged. A question frozen for an
       agent (`InquiryPanel`'s "Ask an agent about this", `store.prepare()`)
       is sent exactly as it was frozen -- its own words, its own immutable
       input package as actual file parts, and its own operation key -- the
       instant the chip it is attached to is still that exact question:
       `selector.perspective` is the fresh durable read `managedSelector` just
       checked the chip against, so agreement here is agreement with the
       record, not with whatever this card happened to be holding. */
    const active = inquiries.snapshot().active
    if (active && selector.perspective?.id === active.perspective) {
      return { post: { ...perspectiveRequest(post, active), [SELECTOR_FIELD]: selector }, op: active.request_op, perspective: active }
    }
    return { post: { ...post, [SELECTOR_FIELD]: selector }, op }
  }
  at.afterRecorded = async (attempt, answer) => {
    if (!attempt.perspective) return
    const requests = answer.expectations
    if (!Array.isArray(requests) || requests.length !== 1 || typeof requests[0] !== 'string') throw new Error('A Perspective question needs exactly one actual agent request. Its frozen intent is kept.')
    const request = requests[0]
    await inquiries.bind(attempt.perspective, request)
    /* BOUND AND RECONCILED: the actual send is now the record's, and
       `reconcile`'s own qualification read is taken once here so the owner
       sees it immediately rather than only once a reply lands. The agent's
       actual reply is frozen as this Perspective's answer later, at the
       recorded agent-reply boundary (`finalizeReply`), once the record shows
       `request` was actually answered -- never here, before any reply exists. */
    await inquiries.reconcile(attempt.perspective, 'display')
    inquiries.update({ active: attempt.perspective, bound: { perspective: attempt.perspective.perspective, request } })
  }

  useEffect(() => { void store.prepare() }, [store])

  /* THE ACTIVE PERSPECTIVE'S CHIP IS BACK WHEN THE CARD IS (owner §6).
     A Magnet reopened with a Perspective selected showed no context at all
     until the owner happened to type while standing on the Perspectives view,
     although the Perspective in force is what the next message is about. So
     the selected Perspective is attached as soon as it is known -- a
     reference and the label the owner can already read, never any content.
     `attachContext` is what applies it, which is what keeps the owner in
     charge of it: it will not replace a chip they attached and will not
     defeat their removal of one, so an intentional Remove stays removed until
     a send or an explicit "Discuss this record". */
  useEffect(() => {
    if (!lens.selected) return
    const row = lens.rows.find((p) => p.perspective === lens.selected)
    attachContext(resource, stamped({ ref: lens.selected, kind: 'perspective', label: row?.name || lens.selected },
      versionOfRow(lens.rows, lens.selected)))
  }, [lens.selected, lens.rows, resource])

  /* AND WHICH VERSION IT STANDS FOR, as soon as this bar can say it. A chip
     may arrive from a view that states no version -- the Perspectives panel
     selecting a lens (`showPerspectiveContext`), an inspected collected record
     -- and one restored from a release that kept none arrives the same way.
     Such a chip is stamped from the durable read the owner is looking at, ONCE:
     a chip that already says what it stands for is never re-stamped, which is
     what makes a later revision a refusal instead of a quiet substitution. */
  useEffect(() => {
    const chip = s.context
    if (!chip || attachedVersion(chip)) return
    const at = chip.kind === 'perspective' ? versionOfRow(lens.rows, chip.ref) : versionOfRecord(s.results, chip.ref)
    if (!at) return
    resource.update({ context: stamped(chip, at) })
  }, [s.context, s.results, lens.rows, resource])

  /* THE CHIP ATTACHES ON THE FIRST MEANINGFUL KEYSTROKE, not on arrival in a
     view and not on every change: the draft going from nothing typed to
     something typed is the moment, and `attachContext` itself refuses to
     replace an attached chip or to defeat the owner's suppression. */
  const draft = mini.draft.trim()
  useEffect(() => {
    const before = typed.current
    typed.current = draft
    if (before || !draft) return
    const row = lens.rows.find((p) => p.perspective === lens.selected)
    const candidate = contextCandidate(resource, row ? { perspective: row.perspective, name: row.name } : null)
    if (candidate) attachContext(resource, candidate.kind === 'perspective'
      ? stamped(candidate, versionOfRow(lens.rows, candidate.ref)) : candidate)
  }, [draft, resource, lens.rows, lens.selected])

  /* WHAT SENDING DOES TO THE CARD, ONCE, WHENEVER THIS BAR CAN NEXT DO IT. The
     footer is not mounted in settings or while the card is closed, and that is
     exactly when a held answer can land: the send's own note (`carried`, in the
     Magnet's working state) is what says there is still an act owing and what
     that act is about. Settling consumes the note, so a remount, a re-render or
     the same key answered twice cannot do it again -- and a reference the owner
     has attached since belongs to the message they are writing now, not to
     this one. */
  useEffect(() => {
    const owed = s.carried, done = mini.sent
    if (!owed || !done || owed.op !== done.op) return
    afterSent(resource, owed)
  }, [mini.sent?.op, s.carried?.op, resource])

  const blocked = !!mini.identity

  return <ComposerBarView
    canWrite={canWrite}
    cannotWriteBecause={cannotWriteBecause}
    unavailable={mini.unavailable}
    chip={s.context}
    suppressed={s.contextSuppressed}
    onRemoveChip={() => removeContext(resource)}
    frozen={blocked || !bound || mini.sending || mini.uncertain}
    sending={mini.sending}
    creating={mini.creating}
    identity={mini.identity}
    contextError={mini.contextError}
    sendError={mini.sendError}
    uncertain={mini.uncertain}
    canRetry={!mini.sending && !blocked && !!bound}
    onRetry={() => {
      const attempt = miniAttempt(resource)
      if (attempt?.request) void store.submit(attempt.request.body, attempt.op, attempt.brain).catch(() => {})
      else void store.send()
    }}
    sent={mini.sent}
    box={box}
    composer={<Composer key={ask.where} conversation={store.conversation}
      /* `references: 'audited'` is the exact-text seam: a reference dropped
         into this composer contributes no separator and no label to the words,
         because this door takes what is selected by identity and validates the
         words against the parts exactly (`composer/draft.ts`, `BodySeam`). */
      /* `attached`: AN INTENTIONALLY ATTACHED REFERENCE IS SOMETHING TO SEND.
         The chip is the card's working state, not a part of the draft, so the
         real Composer would hold Send disabled on a message whose whole point
         is the record it is about. It travels as the audited selector, and a
         selection the card cannot state exactly refuses at the press with its
         own sentence -- so nothing is written to make the button live. */
      asking={{ ...ask, references: 'audited', attached: !!s.context,
        key: `${ask.key}:${mini.replyTo?.id ?? ''}` }}
      replyTo={mini.replyTo?.id ?? null} onClearReply={() => store.replyTo(null)}
      /* WHICH POST IS BEING ANSWERED, in the Magnet's own words: the number and
         the author the card read, because Fluid's own post store does not hold
         this Conversation's posts and would say only "a post" (owner §6). */
      replyTarget={mini.replyTo ? { number: mini.replyTo.number, alias: mini.replyTo.alias } : null}
      operations collapsible />}
  />
}

export interface ComposerBarViewProps {
  canWrite: boolean
  cannotWriteBecause?: string
  unavailable?: string
  chip: MagnetContext | null
  suppressed: boolean
  onRemoveChip(): void
  /** the whole composer is held while a send is unresolved or the page has moved */
  frozen: boolean
  sending: boolean
  creating: boolean
  identity?: string
  contextError?: string
  sendError?: string
  uncertain: boolean
  canRetry: boolean
  onRetry(): void
  sent?: { post: string; number: number | null; replayed: boolean }
  box?: RefObject<HTMLDivElement | null>
  /** the real `fluid/Composer`, supplied so what this bar draws around it can
   *  be asserted without a browser: the Composer itself is client-only. */
  composer: ReactNode
}

/** THE FOOTING NOTE of the approved compose box: the one subtle line the
 *  mockups put at the left of it, saying what sending does here
 *  (`10-current-discussion.png`: "Ordinary discussion" beside Send). It is the
 *  whole of the standing disclosure this box carries -- nothing explains the
 *  mechanism beside the words any more -- and what a particular message is
 *  about is the chip, which is drawn only when there is one. */
export const COMPOSE_NOTE = 'Ordinary discussion'

/** EVERYTHING THE BAR DRAWS AROUND THE COMPOSER. It holds no state and reaches
 *  nothing, so it is the whole of what can be checked without a DOM; the real
 *  Composer inside it is the app's own and is driven by the browser suite.
 *
 *  THE SHAPE IS THE APPROVED `mgd-compose` BOX: bordered, dark, 9px radius,
 *  14px inside, with the words above and a footing row under them -- not the
 *  bare input strip this was. Nothing about sending changes: the field, the
 *  tools, the split send menu and the Send control are `fluid/Composer`'s own,
 *  inside the box, and the write gate above still decides whether this draws a
 *  composer at all. */
export function ComposerBarView(p: ComposerBarViewProps) {
  if (!p.canWrite) {
    return <div className="q2-magnet-composer q2-magnet-composer-readonly">
      <p className="mgd-subtle q2-mini-nowrite">{p.cannotWriteBecause
        ?? 'Sending is unavailable for this Magnet here. Nothing in this card writes to the record.'}</p>
    </div>
  }
  return <div className="q2-magnet-composer" ref={p.box}>
    {p.unavailable === NO_OWN_CONVERSATION && <p className="mgd-subtle" role="status">
      This Magnet has no Conversation of its own yet. Sending makes one and records the message in it.
    </p>}
    {p.unavailable && p.unavailable !== NO_OWN_CONVERSATION && <p className="q2-mini-alert" role="status">{p.unavailable}</p>}
    <div className="mgd-compose q2-magnet-compose-box">
      {/* WHAT THIS MESSAGE IS ABOUT, in ordinary words and without the
          identifier: the reader attached it from a view that showed them the
          thing itself, and the exact identity is what the message carries, not
          what the sentence has to spell out (owner §2). It sits inside the box,
          over the words it belongs to, as the mockups' own tag does. */}
      {p.chip && <p className="mgd-tag q2-magnet-chip">
        <span className="q2-magnet-chip-label">About <b>{contextWords(p.chip)}</b> <small>{CONTEXT_WORDS[p.chip.kind]}</small></span>
        <button type="button" className="mgd-link mgd-small" aria-label={`Remove ${contextWords(p.chip)} from this message`}
          onClick={p.onRemoveChip}>Remove</button>
      </p>}
      {p.suppressed && !p.chip && <p className="mgd-subtle">This message carries nothing with it. Open a record and choose “Discuss this record” to attach one.</p>}
      <fieldset className="q2-mini-composer-controls" disabled={p.frozen}>{p.composer}</fieldset>
      <div className="mgd-row mgd-spread q2-magnet-compose-foot">
        <span className="mgd-subtle">{COMPOSE_NOTE}</span>
        {p.uncertain && <button type="button" className="mgd-button" disabled={!p.canRetry}
          onClick={p.onRetry}>Send again under the same key</button>}
      </div>
    </div>
    {p.contextError && <p className="q2-mini-alert" role="status">{p.contextError}</p>}
    {p.identity && <p className="q2-mini-alert" role="status">{p.identity}</p>}
    {p.sendError && <p className={p.uncertain ? 'q2-mini-alert q2-mini-uncertain' : 'q2-mini-alert'} role="status">{p.sendError}</p>}
    {p.creating && <p className="mgd-subtle" role="status">Creating this Magnet’s Conversation…</p>}
    {p.sent && <p className="q2-mini-sent" role="status">
      {p.sent.replayed
        ? 'That post was already recorded under this key; nothing was recorded a second time.'
        : `Recorded${p.sent.number !== null ? ` as #${p.sent.number}` : ''}.`}
    </p>}
  </div>
}
