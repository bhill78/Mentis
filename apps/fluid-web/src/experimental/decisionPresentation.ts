/* WHAT A DECISION ASKS, IN THE WORDS THE RECORD HOLDS -- and, where the
 * record does not hold them, WHICH WORDS ARE MISSING (owner request
 * ent-6f6d22b5c962; contract ent-40166218c575 §3, §5, part D).
 *
 * Needs You was showing internal references and agent-oriented status where a
 * person needed the question, why it is being asked, what each choice does,
 * and where to look. The record may now carry that, per question, as the
 * normalised `presentation` object the creation contract defines, beside a
 * derived, read-only `presentation_status`. This module is everything the page
 * decides from those two, apart from React and the browser, so it is checkable
 * (`tests/decision_presentation_unit.ts`).
 *
 * THE RULES IT KEEPS:
 *   - NOTHING IS INVENTED. A primary source is shown only where one was
 *     explicitly recorded; an explicit `primary: null` with its reason is not
 *     the same as a decision that never recorded the role at all, and neither
 *     becomes an artifact the owner is told to look at.
 *   - WHAT IS MISSING IS SAID, from record structure and explicit fields only:
 *     no question, no context, an offered alternative with no consequence, a
 *     recorded generated approval with no authorization scope or stage,
 *     presentation data this page does not support.
 *   - AN OLDER DECISION IS NOT A BROKEN ONE. Absence of a primary reference
 *     alone is not an error: where the role was never recorded, that is said.
 *     A structurally sufficient older question is shown as recorded, labelled
 *     as an earlier format.
 *   - WHERE A THING CAME FROM IS SAID ONLY WHERE THE RECORD SAYS IT. Words
 *     that match what Mentis fills in do not establish that nobody wrote
 *     them, and a question beginning "Approve this work?" does not establish
 *     that a run produced it. What cannot be told from the record is said to
 *     be exactly that, and what is missing is still named either way
 *     (ent-9f0291944c9a).
 *   - ANSWER SEMANTICS ARE UNTOUCHED. Nothing here reaches what a reply sends
 *     (./decisions.ts `replyFor`): an option answer is still its question id,
 *     option index and label; own words are still own words; withdrawal still
 *     closes unanswered with a reason. Presentation grants nothing.
 *   - WHERE THE SERVER SAYS THE STATE, the server's word is used. Where it says
 *     nothing -- an older server, or a read that does not carry it -- the state
 *     is derived here from the same structure, so a page never claims a
 *     decision is complete because its server was too old to say.
 *   - ONE VOCABULARY, THE BACKENDS' OWN. A problem is named by the path and
 *     code Python (`mentis/decision_presentation.py`) and Rust
 *     (`crates/mentis-ops/src/decision_presentation.rs`) emit for it, and what
 *     is derived here uses the same rules and the same names. The page then
 *     says the same thing whichever of them answered, and no code reaches the
 *     owner as a code: every one of them has words here (§B2, ent-0fc483e17f76).
 * ------------------------------------------------------------------------ */

/* ------------------------------------------------------------ the contract */

/** What kind of thing the question is, for presentation only: it classifies
 *  nothing about authority, and selecting one obtains no behaviour. */
export type PresentationType = 'artifact_approval' | 'action_approval' | 'choice' | 'free_response'

/** The stage an approval says it covers. An author's declaration, never a gate. */
export type Stage = 'design' | 'implementation' | 'integration' | 'deployment' | 'other'

export const STAGES: Stage[] = ['design', 'implementation', 'integration', 'deployment', 'other']
export const TYPES: PresentationType[] = ['artifact_approval', 'action_approval', 'choice', 'free_response']

export interface RecordRef { kind: 'record'; id: string; label: string }
export interface CommitRef { kind: 'commit'; repository: string; sha: string; label: string }
export interface UrlRef { kind: 'url'; url: string; label: string }
/** A reference exactly as the contract shapes it. A URL is a link, never a
 *  thing to fetch or run. */
export type PresentationRef = RecordRef | CommitRef | UrlRef

export interface Presentation {
  version: number
  type: PresentationType
  scope: string
  stages: Stage[]
  /** an explicit reference, or an explicit `null`: MISSING AND NULL DIFFER */
  primary: PresentationRef | null
  primary_reason?: string | null
  supporting?: PresentationRef[] | null
  applies_when?: string | null
}

export type PresentationState = 'complete' | 'legacy' | 'incomplete' | 'unsupported'
export interface Problem { path: string; code: string }
/** `complete` means the supported structural contract is present. It does NOT
 *  mean independently reviewed, owner approved, source verified, or authorised
 *  to execute. */
export interface PresentationStatus { state: PresentationState; problems: Problem[] }

/* --------------------------------------------------- what it is read from */

/** One question, as much of it as presentation reads. Structural, so the
 *  decision read's `Ask` and a fixture both fit. */
export interface Asked {
  id?: string
  expects?: string
  /** a question of a decision form; absent on an ask asked as its own post */
  form?: string
  question?: string | null
  because?: string | null
  options?: { label: string; consequence?: string }[] | null
  presentation?: unknown
  presentation_status?: unknown
}

/** The form the question belongs to, as much of it as presentation reads. */
export interface Asking {
  because?: string | null
  /** a permission form's operation: a system-produced form, not an ordinary ask */
  operation?: unknown | null
  /** the record says this form was produced from prose */
  from_prose?: boolean | null
  /** the record says this form carries a generated approval over this material */
  approval_artifacts?: string[] | null
}

const text = (v: unknown): string | null => (typeof v === 'string' && v.trim() ? v.trim() : null)
const obj = (v: unknown): Record<string, unknown> | null =>
  v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null

export const letterOf = (i: number) => String.fromCharCode(65 + i)

/** The stored presentation object, as stored: an unknown version is handed
 *  back unchanged, never read as version 1. Null where none was recorded. */
export function presentationOf(ask: Asked | null | undefined): Presentation | null {
  const p = obj(ask?.presentation)
  return p ? (p as unknown as Presentation) : null
}

/** WHAT IS WRONG WITH A DECLARED REFERENCE, in the backends' own paths and
 *  codes (`mentis/decision_presentation.py` at 2f3c2210, `reference`): which
 *  exact part of it cannot be read. `refOf` only answers whether a reference
 *  can be DRAWN; this says what to tell the owner about one that cannot, and
 *  it is what lets this page reach the same conclusion a server that projects
 *  its status reaches -- an id that is not a record identity among it (review
 *  finding R1, ent-be99511604d4).
 *
 *  Its length limits and its unknown-key check are the authoring boundary's,
 *  not read here: a stored reference that is too long is still a reference
 *  that can be looked at. Where a server reports one, it has words (`CODE`). */
export function referenceProblems(v: unknown, path: string): Problem[] {
  const r = obj(v)
  if (!r) return [{ path, code: 'reference_object' }]
  const out: Problem[] = []
  if (!text(r.label)) out.push({ path: path + '.label', code: r.label === undefined ? 'required' : 'nonblank_string' })
  if (r.kind === 'record') {
    if (!(typeof r.id === 'string' && /^(?:ent|opr|adm)-[0-9a-fA-F]+$/.test(r.id))) out.push({ path: path + '.id', code: 'record_identity' })
  } else if (r.kind === 'commit') {
    if (!text(r.repository)) out.push({ path: path + '.repository', code: r.repository === undefined ? 'required' : 'nonblank_string' })
    if (!(typeof r.sha === 'string' && /^[0-9a-fA-F]{40}$/.test(r.sha))) out.push({ path: path + '.sha', code: 'full_commit_hash' })
  } else if (r.kind === 'url') {
    let ok = false
    try {
      const u = new URL(String(r.url))
      ok = (u.protocol === 'http:' || u.protocol === 'https:') && !!u.hostname && !u.username && !u.password
    } catch { ok = false }
    if (!ok) out.push({ path: path + '.url', code: 'http_url' })
  } else {
    out.push({ path: path + '.kind', code: 'unsupported_reference_kind' })
  }
  return out
}

/** A reference object only where it has the exact shape the contract gives
 *  it; anything else is malformed and is reported, never half-read. */
export function refOf(v: unknown): PresentationRef | null {
  const r = obj(v)
  if (!r) return null
  const label = text(r.label)
  if (!label) return null
  if (r.kind === 'record' && text(r.id)) return { kind: 'record', id: text(r.id)!, label }
  if (r.kind === 'commit' && text(r.repository) && text(r.sha)) return { kind: 'commit', repository: text(r.repository)!, sha: text(r.sha)!, label }
  if (r.kind === 'url' && text(r.url)) return { kind: 'url', url: text(r.url)!, label }
  return null
}

/** The words the form constructor itself puts where an author's context would
 *  be. Their presence establishes nothing about why the decision is needed, so
 *  both backends report the context as uncertain rather than present. IT DOES
 *  NOT ESTABLISH THE OPPOSITE EITHER: an author who wrote exactly these words
 *  is indistinguishable, in the record, from one who gave none. */
export const CONSTRUCTOR_BECAUSE = 'a decision only the owner can make'

/** THE RECORD ITSELF SAYING THIS FORM CARRIES A GENERATED APPROVAL: the form
 *  act was recorded with the material the approval was generated over
 *  (`approval_artifacts`, which is what Python passes as `generated`). This is
 *  evidence of origin; the question's wording is not. */
const recordedGenerated = (form?: Asking | null): boolean => Array.isArray(form?.approval_artifacts)

/** THE GENERAL APPROVAL QUESTION, BY ITS RECORDED WORDS ALONE. A run's end
 *  asks "Approve this work?", and so may a person: the wording says what the
 *  question is, NEVER who or what produced it. */
const genericApprovalQuestion = (ask: Asked): boolean =>
  /^approve this work\?/i.test((ask.question ?? '').trimStart())

/** WHETHER THE MISSING AUTHORISATION BOUNDARY OF A GENERATED APPROVAL APPLIES
 *  HERE. BOTH TESTS ARE THE BACKENDS' OWN RULE, mirrored here so a page derives
 *  what a server that projects it would have said. Neither reads any meaning
 *  INTO the question: both only reach the statement that its authorisation
 *  boundary was never recorded, which holds whoever asked it. */
function generatedApproval(ask: Asked, form?: Asking | null): boolean {
  return recordedGenerated(form) || genericApprovalQuestion(ask)
}

/** EACH OFFERED ALTERNATIVE WHOSE RECORDED CONSEQUENCE IS NOT TEXT A PERSON
 *  COULD READ, in the backends' own two names for it. `validated` is the
 *  version 1 path, the one that runs the question through the authoring rules
 *  (`mentis/decision_presentation.py` at 2f3c2210, `validate_question` ->
 *  `text()`): there, a consequence that was never recorded is `required`, and
 *  one recorded blank -- or recorded as something that is not a string at all,
 *  a number, a list, an object -- is `nonblank_string`. The earlier-format read
 *  (`fields`, no presentation) checks only truthiness and reports every one of
 *  them as `required`. Said this way, a page derives the code the server
 *  projects rather than a second name for the same omission (review finding F1,
 *  ent-4ca09a1119c8). */
function consequenceProblems(ask: Asked, validated: boolean): Problem[] {
  const out: Problem[] = []
  ;(ask.options ?? []).forEach((o, i) => {
    const given = (o as { consequence?: unknown } | null | undefined)?.consequence
    if (text(given)) return
    const recorded = validated && given !== undefined && given !== null
    out.push({ path: `options[${i}].consequence`, code: recorded ? 'nonblank_string' : 'required' })
  })
  return out
}

/** What is missing from the record itself, whatever format it is in: these
 *  hold for an older decision and a new one alike, and are named exactly as
 *  the backends name them. */
function structural(ask: Asked, form?: Asking | null, validated = false): Problem[] {
  const out: Problem[] = []
  if (!text(ask.question)) out.push({ path: 'question', code: 'required' })
  const because = text(ask.because) ?? text(form?.because)
  if (!because) out.push({ path: 'because', code: 'required' })
  else if (because === CONSTRUCTOR_BECAUSE) out.push({ path: 'because', code: 'unavailable_or_uncertain' })
  out.push(...consequenceProblems(ask, validated))
  return out
}

/** Whether this question is one the owner may be authorising something by. */
const approving = (t: unknown): boolean => t === 'artifact_approval' || t === 'action_approval'

function derived(ask: Asked, form?: Asking | null): PresentationStatus {
  const p = presentationOf(ask)
  /* THE VERSION 1 PATH IS THE VALIDATED ONE, and it is the one whose names for
     a consequence that is not readable text differ from the earlier format's. */
  const problems = structural(ask, form, !!p && p.version === 1)
  if (!p) {
    /* AN EARLIER FORMAT. A generated approval is the one older shape whose
       missing authorization boundary is identified, exactly as both backends
       identify it: its scope and its stage were never recorded with it. */
    if (generatedApproval(ask, form)) {
      problems.push({ path: 'presentation.scope', code: 'not_recorded' })
      problems.push({ path: 'presentation.stages', code: 'not_recorded' })
    }
    return { state: problems.length ? 'incomplete' : 'legacy', problems }
  }
  if (p.version !== 1) return { state: 'unsupported', problems: [{ path: 'presentation.version', code: 'unsupported_version' }, ...problems] }
  if (!TYPES.includes(p.type)) problems.push({ path: 'presentation.type', code: 'unsupported_type' })
  if (!text(p.scope)) problems.push({ path: 'presentation.scope', code: 'required' })
  if (!Array.isArray(p.stages) || p.stages.some((s) => !STAGES.includes(s))) problems.push({ path: 'presentation.stages', code: 'stage_array' })
  else if (approving(p.type) && p.stages.length === 0) problems.push({ path: 'presentation.stages', code: 'approval_stage_required' })
  const has = Object.prototype.hasOwnProperty.call(p as object, 'primary')
  const declaredPrimary = has ? obj(p.primary) : null
  if (!has) problems.push({ path: 'presentation.primary', code: 'required' })
  else if (p.primary === null) {
    if (!text(p.primary_reason)) problems.push({ path: 'presentation.primary_reason', code: 'required' })
  } else {
    /* THE ONE SOURCE, PART BY PART: which exact part of a declared reference
       cannot be read, as both backends name it -- not one `reference_object`
       for the whole of it, which told nobody what was wrong and did not say
       what a server projecting its own status says (R1-B, ent-be99511604d4). */
    problems.push(...referenceProblems(p.primary, 'presentation.primary'))
  }
  /* AND AN APPROVAL OF SOMETHING SPECIFIC NEEDS ONE EXACT THING, which a
     mutable address is not (contract §2, and both backends' own rule). */
  if (p.type === 'artifact_approval' && (!declaredPrimary || declaredPrimary.kind === 'url')) {
    problems.push({ path: 'presentation.primary', code: 'exact_artifact_required' })
  }
  if (p.type === 'free_response' && (ask.options ?? []).length > 0) problems.push({ path: 'options', code: 'omit_for_free_response' })
  if (p.type === 'choice' && !ask.options) problems.push({ path: 'options', code: 'choice_options_required' })
  /* A NEW APPROVAL MAY NOT BE THE GENERIC ONE: the backends refuse "Approve
     this work?" and nothing else as the whole question of an approval. */
  if (approving(p.type) && /^approve (?:this|the) work[?.! ]*$/i.test((ask.question ?? '').trim())) {
    problems.push({ path: 'question', code: 'specific_approval_question_required' })
  }
  return { state: problems.length ? 'incomplete' : 'complete', problems }
}

/** The state of this question's presentation: THE SERVER'S WORD WHERE IT GAVE
 *  ONE, else the same rules applied here. A state this page does not know is
 *  shown as unsupported with its own problems kept, never read as complete. */
export function statusOf(ask: Asked | null | undefined, form?: Asking | null): PresentationStatus {
  if (!ask) return { state: 'legacy', problems: [] }
  const said = obj(ask.presentation_status)
  if (said) {
    const problems = Array.isArray(said.problems)
      ? (said.problems as unknown[]).map(obj).filter((p): p is Record<string, unknown> => !!p)
        .map((p) => ({ path: String(p.path ?? ''), code: String(p.code ?? '') }))
      : []
    const state = said.state
    if (state === 'complete' || state === 'legacy' || state === 'incomplete' || state === 'unsupported') return { state, problems }
    return { state: 'unsupported', problems: [{ path: 'presentation_status.state', code: 'unsupported-state' }, ...problems] }
  }
  return derived(ask, form)
}

/** WHETHER SOMETHING THIS DECISION NEEDS CANNOT BE READ FROM THE RECORD: an
 *  incomplete new ask, presentation data this page cannot read, or an older
 *  one with an identified omission. Complete, and a structurally sufficient
 *  earlier format, are both clear. It changes what the form OFFERS, never what
 *  anything records. */
export const unclear = (s: PresentationStatus): boolean =>
  s.state === 'incomplete' || s.state === 'unsupported' || (s.state === 'legacy' && s.problems.length > 0)

/** The same, including what only resolving the question's own exact material
 *  shows (`materialGone`): a structurally complete approval whose one named
 *  source is not in this Brain is offered the same ways out as one whose
 *  record is incomplete, and the withdrawal says the same thing on both. And
 *  one whose standing this page has not established yet (`materialUnread`) is
 *  offered them too, for as long as that is so. */
export const unclearNow = (s: PresentationStatus, ask?: Asked | null, standing?: Standing, read?: Reading): boolean =>
  unclear(s) || !!materialGone(ask, standing) || !!materialUnread(ask, read)

/** WHETHER THE RECORD ITSELF SAYS THIS QUESTION MAY AUTHORISE SOMETHING. Its
 *  own declared type where it has one, else the backends' own rule for the
 *  general approval. Nothing is read from an ordinary choice between
 *  alternatives, from a question asked for the owner's words, or from the
 *  wording of anything: a question is an approval here only where the record
 *  says so.
 *
 *  A SYSTEM-PRODUCED PERMISSION FORM IS NOT THIS. Its authority is the
 *  operation it displays, with its own Allow once / Deny consequences
 *  (`OperationLine`); it does not declare presentation metadata and is not
 *  read as an approval that lost some. */
export function asksAuthority(ask: Asked | null | undefined, form?: Asking | null): boolean {
  if (!ask) return false
  if (form?.operation) return false
  const p = presentationOf(ask)
  if (p && p.version === 1) return approving(p.type)
  return generatedApproval(ask, form)
}

/** THE PROBLEMS ONLY AN APPROVAL IS EVER REPORTED WITH. Both backends emit
 *  each of these from a branch they reach only for a question that may
 *  authorise something: the legacy generated-approval boundary
 *  (`presentation.scope` / `presentation.stages` `not_recorded`), and the
 *  version 1 rules that apply to the two approval types alone
 *  (`mentis/decision_presentation.py` at 2f3c2210, `validate_question`). So
 *  THE PROBLEM ITSELF IS THE RECORD'S OWN STATEMENT that this is an approval
 *  AND that what it would authorise is not in the record -- no wording is
 *  interpreted, and no authority is attributed to anything here.
 *
 *  WHY IT IS READ THIS WAY AND NOT FROM THE QUESTION. A decision asked as its
 *  own post carries its recorded question in the Brain but NOT on the wire:
 *  `_expectation_view` projects `question` only for a question of a form, so a
 *  client cannot apply the backends' own generic-approval rule to a standalone
 *  ask at all (review finding R2, ent-be99511604d4). The projected status can,
 *  and does; a page that trusts it says what the server said. */
const APPROVAL_BOUNDARY_UNREAD: Record<string, true> = {
  'question:specific_approval_question_required': true,
  'presentation.scope:not_recorded': true,
  'presentation.stages:not_recorded': true,
  'presentation.stages:approval_stage_required': true,
  'presentation.primary:exact_artifact_required': true,
}

/** THE PROBLEMS THAT MEAN THE SAME THING, BUT ONLY WHERE THE RECORD DECLARES
 *  THE QUESTION AN APPROVAL. Both backends report these for every type, so what
 *  makes them an unreadable authorisation is the declared type, not the code: a
 *  choice between alternatives authorises nothing by itself, and a blank scope
 *  on one leaves its alternatives answerable. */
const DECLARED_BOUNDARY_UNREAD: Record<string, true> = {
  'presentation.scope:required': true,
  'presentation.scope:nonblank_string': true,
  'presentation.stages:stage_array': true,
}

/** REQUIRED APPROVAL MATERIAL THAT CANNOT BE INSPECTED (contract §5): the one
 *  source an approval names was recorded and cannot be read -- not a record id
 *  this Brain could look up, not a whole commit, not an address, not a
 *  reference object at all. Approving material nobody can look at is not an
 *  approval anyone can read, whatever its scope says.
 *
 *  THE ABSENCE OF THE ROLE ITSELF IS NOT THIS. `presentation.primary:required`
 *  says only that whether this decision has a primary source was never
 *  recorded, and the contract is explicit that absence alone is not an error --
 *  an action approval needs no artifact. Where one is REQUIRED and absent, the
 *  backends say so as `exact_artifact_required`, which is above. */
const materialUnreadable = (p: Problem): boolean =>
  (p.path === 'presentation.primary' || p.path.startsWith('presentation.primary.'))
  && !(p.path === 'presentation.primary' && p.code === 'required')

/** WHETHER THIS QUESTION'S OWN AUTHORITY CANNOT BE READ FROM THE RECORD: what
 *  an answer would permit, at which stage, which exact thing, or the material
 *  it names, is among what the record does not hold.
 *
 *  It changes what the form OFFERS, never what anything records, and it reads
 *  no meaning into any option: which of the recorded choices would have
 *  authorised what is exactly what cannot be read (contract ent-40166218c575
 *  §5.4; review findings B4 ent-b2914bea6fb4 and R1/R2 ent-be99511604d4). */
export function authorityUnread(
  status: PresentationStatus, ask: Asked | null | undefined, form?: Asking | null,
): boolean {
  if (!status.problems.length) return false
  /* A SYSTEM-PRODUCED PERMISSION FORM IS NEVER THIS: its authority is the
     operation it displays, with its own Allow once / Deny consequences. */
  if (form?.operation) return false
  const declared = asksAuthority(ask, form)
  return status.problems.some((p) => {
    if (APPROVAL_BOUNDARY_UNREAD[`${p.path}:${p.code}`]) return true
    if (!declared) return false
    return !!DECLARED_BOUNDARY_UNREAD[`${p.path}:${p.code}`] || materialUnreadable(p)
  })
}

/** WHAT CHOOSING ONE OF THE RECORDED ALTERNATIVES WOULD DO, WHERE THE RECORD
 *  DOES NOT HOLD IT. Nothing to do with authority and nothing to do with what
 *  kind of question it is: an offered alternative whose consequence was never
 *  recorded cannot be sent as an informed answer, whether it approves something
 *  or picks between two designs, and offered choices on a question recorded as
 *  asking for the owner's words mean something the record never said
 *  (contract §5, §5.4; review finding R1, ent-be99511604d4).
 *
 *  NOTHING IS SUPPLIED FOR IT. The missing consequence stays missing and is
 *  said to be (`gapWords`); the alternatives stay exactly as recorded. */
/** EVERY CODE EITHER BACKEND PUTS ON AN ALTERNATIVE'S CONSEQUENCE TO SAY IT IS
 *  NOT TEXT ANYBODY CAN READ: never recorded (`required`, and `not_recorded`
 *  from a read that reports absence that way), or recorded blank or recorded as
 *  something that is not text at all (`nonblank_string`). One that is merely
 *  LONGER than the authoring boundary allows (`max_length_2000`) is not among
 *  them, and must not be: those words are in the record and can be read
 *  (review finding F1, ent-4ca09a1119c8). */
const CONSEQUENCE_UNREAD: Record<string, true> = {
  required: true,
  not_recorded: true,
  nonblank_string: true,
}

const choiceMeaningUnread = (p: Problem): boolean =>
  (/^options\[\d+\]\.consequence$/.test(p.path) && !!CONSEQUENCE_UNREAD[p.code])
  || (p.path === 'options' && p.code === 'omit_for_free_response')

/** PRESENTATION DATA THIS PAGE CANNOT READ AT ALL. An unsupported version is
 *  reported alone -- the backends validate nothing else behind it -- so whether
 *  this question approves anything, what it would permit and what its choices
 *  lead to are all unestablished, not established as absent. An unsupported
 *  type and a state this page does not know are the same situation. Its stored
 *  data is preserved and said to be unsupported; what is not done is offer one
 *  of its choices as an answer whose meaning nobody here can establish. */
const UNREADABLE_DATA: Record<string, true> = {
  'presentation.version:unsupported_version': true,
  'presentation.type:unsupported_type': true,
  'presentation_status.state:unsupported-state': true,
}

/* ------------------------------- the material, as this page resolved it now */

/** HOW ONE EXACT REFERENCE STANDS NOW, where this page resolved it BY THAT ID
 *  AND BY NOTHING ELSE. It is the server's own resolution of the id the
 *  question declared (`mentis/fluid/inspect.py` `declared` -> `availability`,
 *  drawn by `quiet2/needs/inspect.ts`), handed here by whoever hosts the form.
 *  `state` is `ok` or what became of it -- missing, deleted, erased, purged,
 *  unreadable -- and `available` is whether there is anything to look at. */
export interface RefStanding { available: boolean; state: string; why?: string | null }

/** What this page resolved for one exact id, or null where it resolved
 *  nothing. A HOST THAT RESOLVES NO REFERENCES SUPPLIES NONE, and then nothing
 *  whatever is claimed about any reference: not that it is there, and not that
 *  it is gone. */
export type Standing = ((id: string) => RefStanding | null | undefined) | null | undefined

/** THE ONE EXACT THING AN APPROVAL OF SOMETHING SPECIFIC NAMES, RESOLVED TO
 *  NOTHING THAT CAN BE INSPECTED (contract ent-40166218c575 §5; review finding
 *  F2, ent-4ca09a1119c8). The record declares the question an approval of
 *  something specific AND declares which exact record that is; this page
 *  resolved that id and the Brain answered that it holds nothing with it, that
 *  it was deleted or erased, or that there is nothing to open. Approving
 *  material nobody can look at is not an approval anyone can read, and the
 *  question's own structure says so -- the page does not judge the material.
 *
 *  WHAT IS DELIBERATELY OUTSIDE IT, so that nothing is inferred:
 *   - ONLY `artifact_approval`, the one declared type both backends refuse
 *     without one exact thing (`exact_artifact_required`). An action approval,
 *     a choice, a question asked for the owner's words and every earlier format
 *     need no artifact, and none is required of them here.
 *   - ONLY THE PRIMARY. Further material a question names (`supporting`) is not
 *     the material it is about, and an unavailable one takes nothing away.
 *   - ONLY A DECLARED RECORD. A commit and an address are named as what they
 *     are and are not resolved in this Brain; a malformed or absent primary is
 *     already the backends' own `record_identity` / `exact_artifact_required`.
 *   - ONLY WHAT WAS RESOLVED. No resolution means nothing is known, which is
 *     not the same as unavailable; and NOTHING IS EVER SUBSTITUTED for the id
 *     the question declared. */
export function materialGone(
  ask: Asked | null | undefined, standing: Standing,
): { ref: RecordRef; stood: RefStanding } | null {
  if (!standing) return null
  const r = requiredRecord(ask)
  if (!r) return null
  const stood = standing(r.id)
  if (!stood || (stood.state === 'ok' && stood.available !== false)) return null
  return { ref: r, stood }
}

/** THE ONE EXACT RECORD AN APPROVAL OF SOMETHING SPECIFIC DECLARES, and null
 *  for every other question there is. It is the one declared type both backends
 *  refuse without one exact thing (`exact_artifact_required`), read from the
 *  record's own declaration and from nothing else -- so NOTHING OPTIONAL AND NO
 *  ACTION REFERENCE IS EVER READ AS REQUIRED: an action approval, a choice
 *  between alternatives, a question asked for the owner's words and every
 *  earlier format answer null, as does a question whose primary is further
 *  material (`supporting`), a commit, an address, an explicit `primary: null`
 *  or a malformed one. */
export function requiredRecord(ask: Asked | null | undefined): RecordRef | null {
  const p = presentationOf(ask)
  if (!p || p.version !== 1 || p.type !== 'artifact_approval') return null
  const r = refOf(p.primary)
  return r && r.kind === 'record' ? r : null
}

/** Said of required approval material that resolved to nothing to look at: the
 *  asker's own words for the thing, and the record's own reason, never a code
 *  and never a guess at what it might have been. */
export const MATERIAL_GONE_UNSAID = 'it could not be read.'
export function materialGoneWords(got: { ref: RecordRef; stood: RefStanding }): string {
  return 'This asks you to approve one exact thing, and that thing cannot be inspected from here: '
    + `“${got.ref.label}” — ${text(got.stood.why) ?? MATERIAL_GONE_UNSAID}`
}

/** WHAT THE PAGE'S OWN READ OF A QUESTION'S REQUIRED MATERIAL HAS COME TO,
 *  where the form resolves references for ITSELF because its host resolves none
 *  (`./materialStanding`, the F2 seam in Fluid's column, post, thread sheet and
 *  full screen and in governance's asks). `settled` is whether that read
 *  answered at all -- NOT what it said: what it said is `Standing`, and
 *  `materialGone` reads it exactly as it reads a host's. `why` is why it has
 *  not answered, in the page's own words, or null while it is still on its way.
 *
 *  A HOST THAT RESOLVES REFERENCES SUPPLIES NONE OF THIS (Quiet Chat's Needs
 *  you): its resolution is in hand when the form is drawn, and nothing here
 *  applies to it. */
export interface MaterialRead { settled: boolean; why: string | null }
export type Reading = MaterialRead | null | undefined

/** REQUIRED APPROVAL MATERIAL THIS PAGE HAS NOT ESTABLISHED THE STANDING OF
 *  YET: the read of it is still on its way, it did not finish, or it was
 *  answered by another Brain than this page is showing.
 *
 *  NOTHING WHATEVER IS CLAIMED ABOUT THE REFERENCE ITSELF. This is not
 *  `materialGone` and never becomes it: it does not say the record is missing,
 *  deleted or present, and when the read answers, what it answered is the only
 *  thing read. What follows from it is one thing only -- a choice whose meaning
 *  this page has not finished establishing is not offered as an answer yet
 *  (`clarifyNeeded`) -- and the owner's own words, Leave open and the
 *  withdrawal are untouched, as is everything already in the record. */
export function materialUnread(
  ask: Asked | null | undefined, read?: Reading,
): { ref: RecordRef; why: string | null } | null {
  if (!read || read.settled) return null
  const r = requiredRecord(ask)
  return r ? { ref: r, why: text(read.why) } : null
}

/** Said while the read of required approval material is still on its way. */
export const MATERIAL_UNREAD_PENDING = 'whether it can be inspected is still being read.'
/** The same, said as what it is: never as the thing being absent. */
export function materialUnreadWords(got: { ref: RecordRef; why: string | null }): string {
  return 'This asks you to approve one exact thing, and whether that thing can be inspected from here is not established yet: '
    + `“${got.ref.label}” — ${got.why ?? MATERIAL_UNREAD_PENDING} `
    + 'Nothing here says this Brain does or does not hold it.'
}

/** WHETHER THIS QUESTION NEEDS CLARIFYING BEFORE ONE OF ITS CHOICES COULD BE
 *  AN ANSWER: something essential to what answering MEANS is not in the record
 *  -- what an answer would authorise, the material it is about, what choosing
 *  an alternative leads to, or presentation data this page cannot read.
 *
 *  IT IS NOT `unclear`, AND THAT IS THE POINT. A decision may be missing
 *  something that leaves every choice readable -- why it is asked, whether it
 *  has a primary source, a question of its own (which a standalone ask never
 *  records: what is asked is its post) -- and that one keeps every control it
 *  had. What is withheld here is only the sending of a recorded choice whose
 *  meaning cannot be established; the choices stay, as recorded, to read, and
 *  the owner's own words, Leave open and the withdrawal are untouched.
 *
 *  A SYSTEM-PRODUCED PERMISSION FORM IS EXCLUDED ENTIRELY: its authority is the
 *  operation it displays, and it declares no presentation metadata to lose. */
export function clarifyNeeded(
  status: PresentationStatus, ask: Asked | null | undefined, form?: Asking | null, standing?: Standing,
  read?: Reading,
): boolean {
  if (form?.operation) return false
  if (status.state === 'unsupported') return true
  /* AND BEFORE EITHER, WHERE THIS PAGE HAS NOT FINISHED ESTABLISHING WHETHER
     THE ONE EXACT THING IT APPROVES CAN BE INSPECTED. A read that has not
     answered is not an answer that the thing is there: until it answers, what
     sending one of the choices would mean is not established here, so none of
     them is sent -- and nothing is said about the reference (F2's seam). */
  if (materialUnread(ask, read)) return true
  /* BEFORE THE PROBLEMS, BECAUSE THIS ONE IS NOT AMONG THEM. A question may be
     structurally complete -- every field the contract asks for, recorded and
     valid -- and the one exact thing it names still be absent from the Brain.
     The backends validate the reference, not what it resolves to, so this is
     the page joining what it already drew to what it already offers (F2). */
  if (materialGone(ask, standing)) return true
  if (!status.problems.length) return false
  if (status.problems.some((p) => !!UNREADABLE_DATA[`${p.path}:${p.code}`])) return true
  if (status.problems.some(choiceMeaningUnread)) return true
  return authorityUnread(status, ask, form)
}

/* ---------------------------------------------------------------- in words */

/** Where the material this decision is about stands: shown, explicitly absent
 *  with the recorded reason, or never recorded at all. Nothing else. */
export type PrimaryStanding =
  | { kind: 'ref'; ref: PresentationRef }
  /** `primary: null` was recorded, with why there is no primary source */
  | { kind: 'none'; because: string | null }
  /** no presentation, or a malformed primary: the role was never recorded */
  | { kind: 'unrecorded' }

export function primaryOf(ask: Asked | null | undefined): PrimaryStanding {
  const p = presentationOf(ask)
  if (!p || !Object.prototype.hasOwnProperty.call(p as object, 'primary')) return { kind: 'unrecorded' }
  if (p.primary === null) return { kind: 'none', because: text(p.primary_reason) }
  const r = refOf(p.primary)
  return r ? { kind: 'ref', ref: r } : { kind: 'unrecorded' }
}

/** The further references the question declares, in the order declared; only
 *  the well-formed ones, so a malformed one is never half-shown. */
export function supportingOf(ask: Asked | null | undefined): PresentationRef[] {
  const p = presentationOf(ask)
  /* NOTHING IS READ OUT OF A VERSION THIS PAGE DOES NOT SUPPORT: the stored
     data is preserved and said to be unsupported, not drawn as version 1's. */
  if (!p || p.version !== 1 || !Array.isArray(p.supporting)) return []
  return p.supporting.map(refOf).filter((r): r is PresentationRef => !!r)
}

/** A reference as a person reads it. Its id is never its name. */
export function refWords(r: PresentationRef): string {
  if (r.kind === 'commit') return `${r.label} (${r.repository} ${r.sha.slice(0, 12)})`
  return r.label
}

/** Where a reference can be opened from inside the form: a record by its
 *  exact id (the host says whether it can), a URL by its address. */
export function refOpens(r: PresentationRef): { record: string } | { url: string } | null {
  if (r.kind === 'record') return { record: r.id }
  if (r.kind === 'url') return { url: r.url }
  return null
}

const STAGE_WORDS: Record<Stage, string> = {
  design: 'the design',
  implementation: 'building it',
  integration: 'integrating it',
  deployment: 'deploying it',
  other: 'something else this request names',
}

/** Which stages an approval says it covers, in running words; '' for none. */
export function stageWords(stages: unknown): string {
  if (!Array.isArray(stages)) return ''
  const words = stages.filter((s): s is Stage => STAGES.includes(s as Stage)).map((s) => STAGE_WORDS[s])
  if (!words.length) return ''
  if (words.length === 1) return words[0]
  return words.slice(0, -1).join(', ') + ' and ' + words[words.length - 1]
}

/** What kind of question it is, for a short kicker over it. */
export const TYPE_WORDS: Record<PresentationType, string> = {
  artifact_approval: 'Approval of something specific',
  action_approval: 'Permission for an action',
  choice: 'A choice between alternatives',
  free_response: 'Something you are asked for',
}

/** What an answer would authorise, as the asker wrote it; null where the
 *  record holds none. Never summarised, never shortened to fit. */
export function scopeWords(ask: Asked | null | undefined): string | null {
  const p = presentationOf(ask)
  return p && p.version === 1 ? text(p.scope) : null
}

/** The asker's own condition on the question. It answers nothing by itself. */
export function appliesWhen(ask: Asked | null | undefined): string | null {
  const p = presentationOf(ask)
  return p && p.version === 1 ? text(p.applies_when) : null
}

/** Each offered alternative with no recorded consequence, by its index. */
export function withoutConsequence(ask: Asked | null | undefined): number[] {
  return (ask?.options ?? []).map((o, i) => (text(o?.consequence) ? -1 : i)).filter((i) => i >= 0)
}

/* ------------------------------------------------- what the record does not say */

/** The exact things a person needs said in their own sentence. Keyed by the
 *  backends' own `path:code`. */
const GAP: Record<string, (ask: Asked, p: Problem) => string | null> = {
  'presentation.version:unsupported_version': (ask) => {
    const v = presentationOf(ask)?.version
    return `This decision carries presentation information in a format this page does not support${typeof v === 'number' ? ` (version ${v})` : ''}. `
      + 'Its question, choices and answers below are exactly as recorded.'
  },
  'presentation.type:unsupported_type': () =>
    'This decision carries presentation information this page does not support. Its question, choices and answers below are exactly as recorded.',
  'presentation_status.state:unsupported-state': () =>
    'The server described this decision in a way this page does not support. Its question, choices and answers below are exactly as recorded.',
  'question:required': (ask) => (ask.form
    ? 'No question of its own was recorded for this one: what is asked is the asking post.'
    : 'No question of its own was recorded for this one: what is asked is the post it was asked on.'),
  'question:specific_approval_question_required': () =>
    'The question recorded here is the general “Approve this work?”, which does not say what would be approved.',
  'because:required': () => 'Why this decision is needed was not recorded.',
  /* WHAT THE RECORD HOLDS, NOT WHO PUT IT THERE. The stored words are exactly
     the phrase Mentis fills in when none was given, and an author may have
     written them: which of the two happened cannot be told from the record,
     and neither of them says why (ent-9f0291944c9a). */
  'because:unavailable_or_uncertain': () =>
    'Why this decision is needed cannot be read from the record: the words stored there are exactly the phrase '
    + 'Mentis fills in when none was given, so whether the asker wrote them cannot be told from the record — '
    + 'either way, the record does not say why you are being asked.',
  'presentation.scope:required': () => 'What an answer here would authorise was not recorded.',
  'presentation.scope:not_recorded': () => 'What an answer here would authorise was not recorded.',
  'presentation.stages:not_recorded': () =>
    'Which stage this covers — the design, building it, integrating it or deploying it — was not recorded.',
  'presentation.stages:stage_array': () => 'Which stage this decision covers was not recorded in a way this page can read.',
  'presentation.stages:approval_stage_required': () =>
    'Which stage this approval covers — the design, building it, integrating it or deploying it — was not recorded.',
  'presentation.primary:required': () => 'Whether this decision has a primary source was not recorded.',
  'presentation.primary:exact_artifact_required': () =>
    'This asks you to approve something specific, and the record does not name which thing.',
  'presentation.primary_reason:required': () => 'The record says this decision has no primary source, and does not say why.',
  'options:omit_for_free_response': () =>
    'This was recorded as asking for your words, and also carries offered choices. What the choices mean here was not recorded.',
  'options:choice_options_required': () =>
    'This was recorded as a choice between alternatives, and the record holds no alternatives to choose between.',
  'options:at_least_two': () => 'This was recorded as a choice, and offers fewer than two alternatives to choose between.',
  'questions:array_length_1_to_20': () => 'This was recorded with more questions than one form may be asked with.',
  'questions:use_shorthand_or_batch': () => 'This was recorded as asking one question and as asking several, at the same time.',
}

/** BOTH HALVES OF THE MISSING BOUNDARY, said once. The backends report the
 *  scope and the stage separately; to a person that is one thing -- that
 *  nothing says what approving it would permit. It is said in two ways, and
 *  WHICH ONE IS USED IS DECIDED BY WHAT THE RECORD HOLDS, never by the words
 *  of the question (ent-9f0291944c9a).
 *
 *  WHERE THE RECORD SAYS SO: the form act carries the material the approval
 *  was generated over, so its origin is the record's own statement. */
export const GENERATED_GAP =
  'This was recorded as a generated approval. What authorisation it asks for, and at which stage, was not recorded with it — '
  + 'so what approving it would permit cannot be read from the record.'

/** WHERE NOTHING SAYS SO: all that is held is a question that begins with the
 *  general approval words, which a person may write as readily as a run's end
 *  produces. The missing boundary is the same and is said the same; where it
 *  came from is left as what it is -- not known from the record. */
export const UNATTRIBUTED_APPROVAL_GAP =
  'What authorisation this asks for, and at which stage, was not recorded with it — '
  + 'so what approving it would permit cannot be read from the record. '
  + 'The record does not say whether this question was written for this work or produced as a general approval at the end of a run.'

/** WHAT PART OF THE RECORD A PROBLEM IS ABOUT, in words. Keyed by the path
 *  with every index removed, so `presentation.supporting[3].label` is the
 *  further material it names. */
const FIELD: Record<string, string> = {
  'question': 'The question itself',
  'because': 'Why this decision is needed',
  'options': 'The choices it offers',
  'options[].label': 'The words of one of its choices',
  'options[].consequence': 'What choosing one of its choices leads to',
  'presentation': 'What this decision says it asks of you',
  'presentation.version': 'The format its presentation is recorded in',
  'presentation.type': 'What kind of question this is',
  'presentation.scope': 'What an answer here would authorise',
  'presentation.stages': 'Which stage this decision covers',
  'presentation.primary': 'The one source this decision is about',
  'presentation.primary.label': 'The words for the source this decision is about',
  'presentation.primary.id': 'The source this decision is about',
  'presentation.primary.sha': 'The commit this decision is about',
  'presentation.primary.repository': 'The repository the commit is in',
  'presentation.primary.url': 'The address of the source this decision is about',
  'presentation.primary.kind': 'What kind of thing the source is',
  'presentation.primary_reason': 'Why there is no source to look at',
  'presentation.supporting': 'The further material it names',
  'presentation.supporting[]': 'One of the further things it names',
  'presentation.supporting[].label': 'The words for one of the further things it names',
  'presentation.supporting[].id': 'One of the further things it names',
  'presentation.supporting[].sha': 'A commit it names',
  'presentation.supporting[].repository': 'The repository of a commit it names',
  'presentation.supporting[].url': 'The address of something it names',
  'presentation.supporting[].kind': 'What kind of thing one of the further things is',
  'presentation.applies_when': 'The condition the asker put on this question',
  'questions': 'The questions this form was asked with',
}

/** WHAT IS WRONG WITH IT, in words. Keyed by the backends' code. */
const CODE: Record<string, string> = {
  required: 'was not recorded.',
  not_recorded: 'was not recorded.',
  nonblank_string: 'was recorded with nothing in it.',
  unavailable_or_uncertain: 'cannot be read from the record.',
  object: 'was not recorded in a shape this page can read.',
  question_object: 'was not recorded in a shape this page can read.',
  reference_object: 'was not recorded as something that can be looked at.',
  record_identity: 'does not name a record by an id this Brain could look up.',
  full_commit_hash: 'does not name a whole commit.',
  http_url: 'does not hold a web address that can be opened.',
  unsupported_reference_kind: 'is of a kind this page has no way to show.',
  unknown_key: 'holds something this page does not know what to do with.',
  unsupported_version: 'is in a format this page does not support.',
  unsupported_type: 'is of a kind this page does not support.',
  stage_array: 'was not recorded as stages this page knows.',
  approval_stage_required: 'was not recorded.',
  exact_artifact_required: 'does not name one exact thing to approve.',
  reference_array_max_24: 'names more material than can be shown here.',
  at_least_two: 'offers fewer than two alternatives.',
  duplicate_label: 'offers two choices whose words are the same.',
  omit_for_free_response: 'was recorded on a question that asks for your words.',
  choice_options_required: 'was not recorded.',
  specific_approval_question_required: 'does not say what would be approved.',
  array_length_1_to_20: 'holds more questions than one form may be asked with.',
  use_shorthand_or_batch: 'was recorded in two ways at once.',
}

/** The path with its indexes removed: `options[2].consequence` is about the
 *  same part of the record as `options[0].consequence`. */
const family = (path: string) => path.replace(/\[\d+\]/g, '[]')

/** Said when the record says it in words nobody here has written yet. It names
 *  no field path and no code: an internal path in front of the owner is the
 *  defect this repairs (ent-0fc483e17f76 §B2). */
const UNNAMED_GAP = 'Something this decision records could not be read, and this page has no words for what it was.'

/** ONE PROBLEM, AS A PERSON READS IT. Its own sentence where it has one; else
 *  what part of the record it is about and what is wrong with it, both in
 *  ordinary words; else that something could not be read. */
export function gapWords(p: Problem, ask?: Asked | null): string {
  const a = ask ?? {}
  const m = /^options\[(\d+)\]\.consequence$/.exec(p.path)
  if (m && CONSEQUENCE_UNREAD[p.code]) {
    const i = Number(m[1])
    const label = text((a.options ?? [])[i]?.label)
    /* RECORDED WITH NOTHING IN IT IS NOT THE SAME AS NEVER RECORDED, and both
       differ again from something recorded that is not words at all. The
       backends report the last two under one code; which of them it is is read
       from the stored option itself, and the owner is told the one that is so. */
    const given = ((a.options ?? [])[i] as { consequence?: unknown } | undefined)?.consequence
    const unsaid = p.code !== 'nonblank_string' ? 'was not recorded'
      : typeof given === 'string' ? 'was recorded with nothing in it'
        : 'was not recorded as words'
    return `Choice ${letterOf(i)}${label ? ` “${label}”` : ''}: what choosing it leads to ${unsaid}.`
  }
  const say = GAP[`${p.path}:${p.code}`]
  if (say) {
    const words = say(a, p)
    if (words) return words
  }
  const what = FIELD[family(p.path)]
  const wrong = CODE[p.code] ?? (/^max_length_\d+$/.test(p.code) ? 'is longer than the record allows.' : null)
  return what && wrong ? `${what} ${wrong}` : UNNAMED_GAP
}

/** WHAT THE OWNER WOULD BE DECIDING WITHOUT: each specific thing the record
 *  does not say, in the order the problems were found. Said before the
 *  decision is made; it never blocks one, and it adds no meaning. */
export function gapsOf(status: PresentationStatus, ask: Asked | null | undefined, form?: Asking | null, standing?: Standing, read?: Reading): string[] {
  const a = ask ?? {}
  const out: string[] = []
  /* WHAT IT IS ABOUT COMES FIRST. Required approval material that resolved to
     nothing to look at is said before the question's other omissions, because
     it is the thing the decision is on (F2). Where this page has not finished
     reading how it stands, THAT is said instead, as what it is -- the two are
     never one sentence, because one is about the record and the other is about
     this page's own read of it. */
  const gone = materialGone(ask, standing)
  if (gone) out.push(materialGoneWords(gone))
  const unread = materialUnread(ask, read)
  if (!gone && unread) out.push(materialUnreadWords(unread))
  /* THE MISSING BOUNDARY'S TWO HALVES ARE ONE THING TO A PERSON -- and whether
     the record says where the approval came from decides which sentence says
     it. Only `approval_artifacts` is that evidence; a question that begins
     with the general approval words is not. */
  const has = (path: string, code: string) => status.problems.some((p) => p.path === path && p.code === code)
  const missing = has('presentation.scope', 'not_recorded') && has('presentation.stages', 'not_recorded')
  const said = recordedGenerated(form) ? GENERATED_GAP : UNATTRIBUTED_APPROVAL_GAP
  for (const p of status.problems) {
    if (missing && p.code === 'not_recorded' && (p.path === 'presentation.scope' || p.path === 'presentation.stages')) {
      if (!out.includes(said)) out.push(said)
      continue
    }
    const words = gapWords(p, a)
    if (words && !out.includes(words)) out.push(words)
  }
  return out
}

/* ----------------------------------------------- what closing it does, exactly */

/** Said over a structurally sufficient older question: shown as recorded, and
 *  not claimed to have had its authorisation meaning declared or verified. */
export const EARLIER_FORMAT =
  'Recorded in an earlier format: what it authorises, and the role of the material it names, were not separately declared. '
  + 'Its question, choices and answers below are exactly as recorded.'

/** The condition on a question, and what it does not do. */
export const APPLIES_WHEN_SAYS =
  'This is the asker’s own condition. It never answers, withdraws or skips this question by itself.'

/** WHAT WITHDRAWING DOES. It closes the question unanswered with the owner's
 *  reason; it does not launch a worker, and it promises no clearer question. */
export const WITHDRAW_CLOSES =
  'Withdraw closes this question without answering it. Your reason is recorded as your reply, and the question and its choices stay in the record, unchanged.'
export const WITHDRAW_RESUMES_FORM =
  'When every question in this form is closed, the Work may resume under its existing rules. This does not itself create a replacement question.'
export const WITHDRAW_RESUMES_ALONE =
  'Once it is closed, the Work it belongs to may resume under its existing rules. This does not itself create a replacement question.'

/** The whole disclosure shown before a withdrawal is sent. */
export const withdrawSays = (onForm: boolean): string =>
  `${WITHDRAW_CLOSES} ${onForm ? WITHDRAW_RESUMES_FORM : WITHDRAW_RESUMES_ALONE}`

/** WHY THE RECORDED CHOICES ARE NOT OFFERED HERE, and what is. Said where
 *  something essential to what answering MEANS is not in the record
 *  (`clarifyNeeded`): what an answer would authorise, the material it is about,
 *  what choosing an alternative leads to, or presentation data this page cannot
 *  read. Sending one of the choices would record an answer whose meaning nobody
 *  can establish, and which of them would mean what is precisely what the
 *  record does not say -- so none of them is offered, and no guess is made
 *  about which would have been safe. WHAT EXACTLY IS MISSING IS SAID ABOVE
 *  THIS, per problem, in its own words (`gapsOf`); this sentence says what
 *  follows from it. What closes the question instead is the owner's own words;
 *  Leave open and the withdrawal keep it open or close it unanswered. */
/** WHY THE RECORDED CHOICES ARE NOT OFFERED WHILE THIS PAGE'S OWN READ OF THE
 *  REQUIRED MATERIAL HAS NOT ANSWERED (`materialUnread`). It is deliberately a
 *  DIFFERENT sentence from `CLARIFICATION_NEEDED`: nothing is missing from the
 *  record here, and nothing is claimed about the thing the question names --
 *  what is not established is this page's own reading of how it stands. */
export const CLARIFICATION_PENDING =
  'What sending one of these choices would mean is not established here yet: whether the one exact thing this approves can be inspected has not been read — what is known is said above. '
  + 'So the choices it offered are not offered as answers until it is. Nothing here says that thing is missing from this Brain. '
  + 'They are below as recorded, to read. '
  + 'To answer anyway, answer in your own words; Leave open and Withdraw with a clarification reason are unchanged.'

export const CLARIFICATION_NEEDED =
  'What sending one of these choices would mean is not in the record — what is missing is said above, exactly as it stands — '
  + 'so the choices it offered are not offered as answers: which of them would mean what is part of what the record does not say. '
  + 'They are below as recorded, to read. '
  + 'To settle it, answer in your own words; to leave it for a clearer question, use Leave open or Withdraw with a clarification reason.'

/** WHY AN ANSWER THAT WAS ATTEMPTED AND NEVER CONFIRMED IS NOT SENT AGAIN FROM
 *  HERE (review finding F3, ent-4ca09a1119c8). Recovery must not become the one
 *  path that records an ambiguous choice after the page knows the question
 *  needs clarifying: a kept choice whose meaning cannot be established is held,
 *  not sent. NOTHING IS GIVEN UP BY HOLDING IT. The words are kept exactly as
 *  they were typed, under the same operation key, so if the first request did
 *  land it is still that one post and never a second; asking what became of it
 *  is a read and stays offered; and giving it up is the server's to answer, so
 *  an answer that was recorded after all is found and said, not overwritten. */
/** WHAT IS SAID OF A CHOICE THE FORM READ THE MATERIAL FOR AGAIN AT THE MOMENT
 *  OF SENDING IT, and did not establish (review finding B2, ent-5b7ef83a4e40).
 *  Nothing was sent and nothing was spent; what the question says of the
 *  material now is said above it, in its own words. */
export const CLARIFICATION_HOLDS_SEND =
  'This was not sent: how the one exact thing it approves stands was read again just now, and that read did not establish it. '
  + 'Nothing was recorded and your words are kept. What the read came to is said above.'

export const CLARIFICATION_HOLDS_RESEND =
  'This answer was attempted before the record was read this way, and it chose one of the alternatives — so it is not sent again from here: '
  + 'what sending it would mean is part of what the record does not say, as above. Your words are kept, exactly as you typed them. '
  + 'Check again asks whether it was recorded after all; Change it first asks the server to give it up, and hands your words back if nothing was recorded.'

/** The recorded choices, as the thing they are here: wording, read in full. */
export const CHOICES_AS_RECORDED =
  'the choices it offered, exactly as recorded; none of them can be sent from here'

/** A withdrawal offered as the way out of a question that cannot be read: the
 *  same withdrawal payload and the same editable reason, said as what it is. */
export const WITHDRAW_CLARIFY_LABEL = 'Withdraw with a clarification reason'
export const WITHDRAW_CLARIFY_THEN = 'close it unanswered, with your reason for asking for a clearer question'

/** AN ANSWER IN YOUR OWN WORDS IS AN ANSWER. Said before it is sent, so
 *  "please clarify" is not typed into it as a passive request. */
export const OWN_WORDS_CLOSES = 'Your own words are recorded as your answer and close this question.'
export const OWN_WORDS_NOT_A_CLARIFICATION =
  'Writing “please clarify” here answers the question rather than asking for a clearer one. To leave it for a clearer question, use Leave open, or Withdraw with a clarification reason.'

/** What the one answer action does, for its own tooltip: no promise that an
 *  answer launches work, and no claim that nothing can follow from it. */
export const ANSWER_SAYS_FORM =
  'Records each answer as your reply and closes its question. When every question in this form is closed, the Work may resume under its existing rules.'
export const ANSWER_SAYS_ALONE =
  'Records your answer as your reply and closes this question. The Work it belongs to may then resume under its existing rules.'
export const WITHDRAW_SAYS_FOOT =
  'Closes it without an answer and records your reason. The Work it belongs to may then resume under its existing rules.'
