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
 *   - ANSWER SEMANTICS ARE UNTOUCHED. Nothing here reaches what a reply sends
 *     (./decisions.ts `replyFor`): an option answer is still its question id,
 *     option index and label; own words are still own words; withdrawal still
 *     closes unanswered with a reason. Presentation grants nothing.
 *   - WHERE THE SERVER SAYS THE STATE, the server's word is used. Where it says
 *     nothing -- an older server, or a read that does not carry it -- the state
 *     is derived here from the same structure, so a page never claims a
 *     decision is complete because its server was too old to say.
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

/** What is missing from the record itself, whatever format it is in: these
 *  hold for an older decision and a new one alike. */
function structural(ask: Asked, form?: Asking | null): Problem[] {
  const out: Problem[] = []
  /* An ask asked as its own post HAS no question of its own -- the post is the
     question -- so only a question of a form can be missing one. */
  if (ask.form && !text(ask.question)) out.push({ path: 'question', code: 'required' })
  if (!text(ask.because) && !text(form?.because)) out.push({ path: 'because', code: 'required' })
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
    /* AN EARLIER FORMAT. A generated approval the record itself names (its
       form carries the material it was generated over) is the one older shape
       whose missing authorization boundary is identified: that is explicit
       record structure, not a guess from its wording. */
    if (Array.isArray(form?.approval_artifacts)) problems.push({ path: 'approval.scope', code: 'required' })
    return { state: 'legacy', problems }
  }
  if (p.version !== 1) return { state: 'unsupported', problems: [{ path: 'presentation.version', code: 'unsupported-version' }, ...problems] }
  if (!TYPES.includes(p.type)) return { state: 'unsupported', problems: [{ path: 'presentation.type', code: 'unsupported-type' }, ...problems] }
  if (!text(p.scope)) problems.push({ path: 'presentation.scope', code: 'required' })
  if (!Array.isArray(p.stages)) problems.push({ path: 'presentation.stages', code: 'required' })
  else if (approving(p.type) && p.stages.length === 0) problems.push({ path: 'presentation.stages', code: 'required-for-approval' })
  const has = Object.prototype.hasOwnProperty.call(p as object, 'primary')
  if (!has) problems.push({ path: 'presentation.primary', code: 'required' })
  else if (p.primary === null) {
    if (!text(p.primary_reason)) problems.push({ path: 'presentation.primary_reason', code: 'required' })
    if (p.type === 'artifact_approval') problems.push({ path: 'presentation.primary', code: 'required-for-artifact-approval' })
  } else if (!refOf(p.primary)) problems.push({ path: 'presentation.primary', code: 'malformed' })
  if (p.type === 'free_response' && (ask.options ?? []).length > 0) problems.push({ path: 'options', code: 'not-allowed-for-free-response' })
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

const GAP: Record<string, (ask: Asked, p: Problem) => string | null> = {
  'presentation.version:unsupported-version': (ask) => {
    const v = presentationOf(ask)?.version
    return `This decision carries presentation information in a format this page does not support${typeof v === 'number' ? ` (version ${v})` : ''}. `
      + 'Its question, choices and answers below are exactly as recorded.'
  },
  'presentation.type:unsupported-type': () =>
    'This decision carries presentation information this page does not support. Its question, choices and answers below are exactly as recorded.',
  'presentation_status.state:unsupported-state': () =>
    'The server described this decision in a way this page does not support. Its question, choices and answers below are exactly as recorded.',
  'question:required': () => 'No question of its own was recorded for this one: what is asked is the asking post.',
  'because:required': () => 'Why this decision is needed was not recorded.',
  'presentation.scope:required': () => 'What an answer here would authorise was not recorded.',
  'presentation.stages:required': () => 'Which stage this decision covers was not recorded.',
  'presentation.stages:required-for-approval': () =>
    'Which stage this approval covers — the design, building it, integrating it or deploying it — was not recorded.',
  'presentation.primary:required': () => 'Whether this decision has a primary source was not recorded.',
  'presentation.primary:required-for-artifact-approval': () =>
    'This asks you to approve something specific, and the record does not name which thing.',
  'presentation.primary:malformed': () => 'The primary source recorded for this decision could not be read as a reference.',
  'presentation.primary_reason:required': () => 'The record says this decision has no primary source, and does not say why.',
  'options:not-allowed-for-free-response': () =>
    'This was recorded as asking for your words, and also carries offered choices. What the choices mean here was not recorded.',
  'approval.scope:required': () =>
    'This was recorded as a generated approval. What authorisation it asks for, and at which stage, was not recorded with it — '
    + 'so what approving it would permit cannot be read from the record.',
}

/** WHAT THE OWNER WOULD BE DECIDING WITHOUT: each specific thing the record
 *  does not say, in the order the problems were found. Said before the
 *  decision is made; it never blocks one, and it adds no meaning. */
export function gapsOf(status: PresentationStatus, ask: Asked | null | undefined): string[] {
  const a = ask ?? {}
  const out: string[] = []
  for (const p of status.problems) {
    const m = /^options\[(\d+)\]\.consequence$/.exec(p.path)
    if (m && p.code === 'required') {
      const i = Number(m[1])
      const label = text((a.options ?? [])[i]?.label)
      out.push(`Choice ${letterOf(i)}${label ? ` “${label}”` : ''}: what choosing it leads to was not recorded.`)
      continue
    }
    const say = GAP[`${p.path}:${p.code}`]
    const words = say ? say(a, p) : `The record is missing ${p.path} (${p.code}).`
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
