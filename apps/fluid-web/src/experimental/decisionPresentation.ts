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

/** What is missing from the record itself, whatever format it is in: these
 *  hold for an older decision and a new one alike, and are named exactly as
 *  the backends name them. */
function structural(ask: Asked, form?: Asking | null): Problem[] {
  const out: Problem[] = []
  if (!text(ask.question)) out.push({ path: 'question', code: 'required' })
  const because = text(ask.because) ?? text(form?.because)
  if (!because) out.push({ path: 'because', code: 'required' })
  else if (because === CONSTRUCTOR_BECAUSE) out.push({ path: 'because', code: 'unavailable_or_uncertain' })
  const options = ask.options ?? []
  options.forEach((o, i) => { if (!text(o?.consequence)) out.push({ path: `options[${i}].consequence`, code: 'required' }) })
  return out
}

/** Whether this question is one the owner may be authorising something by. */
const approving = (t: unknown): boolean => t === 'artifact_approval' || t === 'action_approval'

function derived(ask: Asked, form?: Asking | null): PresentationStatus {
  const problems = structural(ask, form)
  const p = presentationOf(ask)
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
  if (!has) problems.push({ path: 'presentation.primary', code: 'required' })
  else if (p.primary === null) {
    if (!text(p.primary_reason)) problems.push({ path: 'presentation.primary_reason', code: 'required' })
    if (p.type === 'artifact_approval') problems.push({ path: 'presentation.primary', code: 'exact_artifact_required' })
  } else if (!refOf(p.primary)) problems.push({ path: 'presentation.primary', code: 'reference_object' })
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

/** THE PROBLEMS THAT MEAN NOBODY CAN READ WHAT AN ANSWER WOULD AUTHORISE: what
 *  it authorises, at which stage, or -- for an approval of something specific
 *  -- which thing. Each is the backends' own `path:code`. Everything else a
 *  question may be missing (its context, one alternative's consequence, the
 *  role of its material) leaves the authorisation itself readable. */
const AUTHORITY_UNREAD: Record<string, true> = {
  'question:specific_approval_question_required': true,
  'presentation.scope:required': true,
  'presentation.scope:not_recorded': true,
  'presentation.scope:nonblank_string': true,
  'presentation.stages:not_recorded': true,
  'presentation.stages:approval_stage_required': true,
  'presentation.stages:stage_array': true,
  'presentation.primary:exact_artifact_required': true,
}

/** WHETHER THIS QUESTION'S OWN AUTHORITY CANNOT BE READ FROM THE RECORD: it is
 *  one the owner may authorise something by, AND what that would permit is one
 *  of the things the record does not hold. It is narrower than `unclear` on
 *  purpose: an ordinary decision missing something else -- why it is asked, one
 *  alternative's consequence, whether it has a primary source -- is still an
 *  ordinary decision, answered the way it always was.
 *
 *  It changes what the form OFFERS, never what anything records, and it reads
 *  no meaning into any option: which of the recorded choices would have
 *  authorised what is exactly what cannot be read (contract ent-40166218c575
 *  §5.4; review finding B4, ent-b2914bea6fb4). */
export function authorityUnread(
  status: PresentationStatus, ask: Asked | null | undefined, form?: Asking | null,
): boolean {
  if (!status.problems.length) return false
  if (!asksAuthority(ask, form)) return false
  return status.problems.some((p) => !!AUTHORITY_UNREAD[`${p.path}:${p.code}`])
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
  if (m && (p.code === 'required' || p.code === 'not_recorded')) {
    const i = Number(m[1])
    const label = text((a.options ?? [])[i]?.label)
    return `Choice ${letterOf(i)}${label ? ` “${label}”` : ''}: what choosing it leads to was not recorded.`
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
export function gapsOf(status: PresentationStatus, ask: Asked | null | undefined, form?: Asking | null): string[] {
  const a = ask ?? {}
  const out: string[] = []
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

/** WHY THE RECORDED CHOICES ARE NOT OFFERED HERE, and what is. Said where the
 *  question's own authority cannot be read (`authorityUnread`): sending one of
 *  its choices would record an authorisation whose boundary nobody can read,
 *  and which of them would have authorised what is precisely what the record
 *  does not say -- so none of them is offered, and no guess is made about which
 *  would have been safe. What closes the question instead is the owner's own
 *  words; Leave open and the withdrawal keep it open or close it unanswered. */
export const CLARIFICATION_NEEDED =
  'What an answer here would authorise is not in the record, so the choices it offered are not offered as answers: '
  + 'which of them would permit what is exactly what the record does not say. They are below as recorded, to read. '
  + 'To settle it, answer in your own words; to leave it for a clearer question, use Leave open or Withdraw with a clarification reason.'

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
