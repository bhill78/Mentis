import type { RouteResult, RouteSource } from '../../fluid/surface/magnet/route'
import type { MagnetConfig } from '../../fluid/surface/magnet/types'

export interface SavedMagnet { id: `mag-${string}`; name: string; config?: MagnetConfig & { schema_version?: number }; reason?: string }

/** The approved hybrid order. Summary is first and the default; `All` is the
 *  real key the owner's design labels "All" (v1 called it `Overview`). */
export const MAGNET_TABS = ['Summary', 'All', 'Posts', 'Files', 'Perspectives', 'Conversation'] as const
export type MagnetTab = typeof MAGNET_TABS[number]
/** An overlay is a place of its own: it keeps its own reading position. */
export type MagnetOverlay = null | 'search' | 'settings'
export type MagnetPlaceKey = MagnetTab | 'search' | 'settings'
export const MAGNET_PLACE_KEYS = [...MAGNET_TABS, 'search', 'settings'] as const

/** Everything one view remembers about where the reader was in it. */
export interface MagnetPlace {
  scroll: number
  inspected: string | null
  inspectScroll: number
  inspectOrigin: string | null
  provenance: boolean
  history: boolean
}

export type MagnetSearchKind = 'Summary' | 'Posts' | 'Files' | 'Perspectives' | 'Conversation' | 'Settings' | 'Batches'
export type MagnetSearchType = 'All' | MagnetSearchKind
export const MAGNET_SEARCH_TYPES = ['All', 'Summary', 'Posts', 'Files', 'Perspectives', 'Conversation', 'Settings', 'Batches'] as const
/** The one result the reader opened from the results list.
 *
 *  `entry` is the index key of the `SearchEntry` that was opened, and is the
 *  identity a return reads the result back by. It is carried because a source's
 *  entry key is its own and is NOT required to be any id its `open()` inspects:
 *  `evidenceSource` keys an entry `evidence:post:<id>` and inspects `<id>`, and
 *  `perspectiveSource` keys `perspective:<p>` and opens `<p>`. Resolving a
 *  target against the index by the inspected id alone therefore finds nothing
 *  for the real sources, which is why the key itself is recorded here.
 *
 *  `item`, `lens` and `message` stay what they always were: what the owning
 *  view needs to render the thing itself, derived from what `open()` actually
 *  did. A target persisted by a build before this field carries no `entry`, so
 *  resolution still falls back to those. */
export interface MagnetSearchTarget { kind: MagnetSearchKind; entry?: string; item?: string; lens?: string; message?: string }

/** A deep snapshot of where the reader was, taken before navigating away.
 *  `searchTarget` and `placeSnapshot` are copies, never live references: that
 *  is what makes a return survive an intervening search. */
export interface MagnetRoute {
  tab: MagnetTab
  overlay: MagnetOverlay
  searchTarget: MagnetSearchTarget | null
  lens: string | null
  query: string
  searchType: MagnetSearchType
  searchListScroll: number
  placeKey: MagnetPlaceKey
  placeSnapshot: MagnetPlace
}

/** One searchable thing a view holds. `open()` navigates to it. */
export interface SearchEntry { key: string; kind: MagnetSearchKind; title: string; text: string; open(): void }
/** A view's contribution to the universal Magnet index. `entries()` is what is
 *  already in hand; `complete()` owes everything else that source holds, so the
 *  index is over collected information and not over what happened to be loaded.
 *  `bound()` is the honest sentence when `complete()` cannot finish. */
export interface SearchSource {
  entries(): SearchEntry[]
  complete?(query: string, signal?: AbortSignal): Promise<SearchEntry[]>
  queryDependent?: boolean
  bound?(): string | null
}

/** The composer's discussion reference. Only the reference and its label are
 *  persisted: captured collection text never enters device storage. */
export interface MagnetContext {
  ref: string
  kind: 'post' | 'file' | 'image' | 'attachment' | 'perspective' | 'batch'
  label: string
  text?: string
}

/** WHAT ONE SEND TOOK WITH IT, written when it goes out and read when it is
 *  recorded. The answer can land while the footer is not mounted -- the card
 *  closed, or settings open -- so what the sent message carried cannot be read
 *  off the card at that point: by then it is the next message's. Held under the
 *  send's own key, so the recorded post settles its own send exactly once. */
export interface MagnetCarried {
  op: string
  context: MagnetContext | null
  suppressed: boolean
  /** where it was written from, taken while that view was still on the screen */
  from: MagnetRoute
}

export interface MagnetSnapshot {
  // identity and liveness -- never persisted
  title: string; loading: boolean; error?: string; summary?: RouteSource
  results: RouteResult[]; next?: string; status?: string; reason?: string
  activation?: { post: string; artifact: { ref: string; digest?: string; size?: number; media_type?: string }; at: number; state: string } | null
  collecting?: boolean; collectionMessage?: string
  // persisted working state (localStorage; workingState.ts maps v1 onto exactly these)
  x: number; y: number; open: boolean; wide: boolean; tab: MagnetTab; overlay: MagnetOverlay
  places: Record<MagnetPlaceKey, MagnetPlace>
  query: string; searchType: MagnetSearchType; searchTarget: MagnetSearchTarget | null; searchListScroll: number
  lens: string | null
  returnRoute: MagnetRoute | null; settingsReturn: MagnetRoute | null
  context: MagnetContext | null; contextSuppressed: boolean
  carried: MagnetCarried | null
  agentId?: string
  assistanceMode?: 'ordinary' | 'retained'
  batchSelection?: { ref: string; digest: string }
  // open-transition baseline (in memory, per tab, as before)
  previousOpen?: number; openedAt?: number
}
export interface MagnetResource {
  id: string; brainKey: string; saved: SavedMagnet;
  snapshot(): MagnetSnapshot; subscribe(fn: () => void): () => void;
  update(change: Partial<MagnetSnapshot>): void;
  read(more?: boolean): Promise<void>; cancel(): void; dispose(): void;
  collect?(): Promise<void>;
  selectBatch?(batch: { ref: string; digest: string } | null): Promise<void>;
}
export type MagnetGet = (path: string, signal?: AbortSignal) => Promise<{ status: number; body: unknown }>

/* ========================================================================
 * MESSAGE BOUNDARY -- the shared contract
 *
 * Revised contract adm-c5c73679ac1e sections 2-5, owner request ent-3191baeb33d2,
 * which accepts both BLOCKING findings of contract review adm-41c083ce0dc9.
 * Published by the Integrator so A (transport/server), D (composer/chips),
 * B (definition snapshot), C (suppression) and E (selected question) build
 * against ONE set of signatures, bounds and digests instead of five
 * compatible-looking ones.
 *
 * What this module is: the executable shape of the boundary -- the selector,
 * what "explicitly empty" means, the exact authored text/parts relationship,
 * the canonical digest and the route's vocabulary. What it is NOT: the route
 * itself. Classification is the SERVER's, from resolved origin/destination
 * and the record's own association (section 2); nothing here lets a client declare
 * its own route, and no type here grants reach or authority (section 5).
 *
 * Cross-language parity is pinned by the golden vectors in
 * apps/fluid-web/tests/fixtures/magnet_boundary_vectors.json, checked from TS
 * by tests/quiet_magnet_contract_unit.ts and from Python by
 * tests/test_magnet_boundary_contract.py. Change a rule here and both fail.
 * ===================================================================== */

/** The one managed schema/policy version this build writes and accepts (section 2). */
export const MANAGED_CONTEXT_VERSION = 1
/** Every new managed send goes through the audited request door. A direct post
 *  into a resolved managed destination refuses; there is no /posts fallback
 *  and no silent context loss (section 2). */
export const MANAGED_REQUEST_DOOR = '/fluid/api/requests'

/* Concrete bounds (section 3). They are part of the contract, not tuning: a value
 * accepted on one side and refused on the other is the defect this prevents. */
/** Submitted selector, as canonical UTF-8 bytes. */
export const SELECTOR_MAX_BYTES = 16 * 1024
export const SELECTOR_MAX_REFERENCES = 16
/** Hydrated canonical context. Overflow refuses; it is never truncated. */
export const HYDRATED_CONTEXT_MAX_BYTES = 64 * 1024
export const IDENTIFIER_MAX_CHARS = 128
export const DIGEST_HEX_CHARS = 64

/** SHA-256 as exactly 64 lowercase hexadecimal characters (section 3). */
export type Sha256Hex = string

/** One durable saved question version in THIS Magnet. `question_digest` is the
 *  digest of that version's text, so a later revision cannot be mistaken for
 *  the one the owner selected (sections 3 and 4). */
export interface MagnetPerspectiveSelection {
  id: string
  question_ref: string
  question_digest: Sha256Hex
}

export const SELECTOR_REFERENCE_KINDS = ['post', 'artifact', 'collected_item'] as const
export type MagnetSelectorReferenceKind = typeof SELECTOR_REFERENCE_KINDS[number]

/** One selected object. `version` is its exact authored revision for a post,
 *  its recorded batch identity for a collected item, and null for an immutable
 *  artifact. Ref and digest identify the object; they are NOT authority, and
 *  they carry no caller text, label, instruction, permission or work (sections 3 and 5). */
export interface MagnetSelectorReference {
  kind: MagnetSelectorReferenceKind
  ref: string
  version: string | null
  digest: Sha256Hex
}

/** Explicit selector v1: exactly these five keys, no more and no fewer (section 3). */
export interface MagnetSelectorV1 {
  version: typeof MANAGED_CONTEXT_VERSION
  mode: 'ordinary'
  configuration_digest: Sha256Hex
  perspective: MagnetPerspectiveSelection | null
  references: MagnetSelectorReference[]
}
export const SELECTOR_V1_KEYS = ['version', 'mode', 'configuration_digest', 'perspective', 'references'] as const

/** The envelope field the selector travels in. */
export const SELECTOR_FIELD = 'magnet_context'

/** EXPLICIT EMPTY SELECTION. Not `{}` -- an empty object is malformed and
 *  refuses. "Nothing selected" is this: the full v1 object saying so, with a
 *  null Perspective and no references. Null and empty selections stay absent;
 *  an active Perspective is never inferred on send (section 3). */
export const emptySelectorV1 = (configuration_digest: Sha256Hex): MagnetSelectorV1 =>
  ({ version: MANAGED_CONTEXT_VERSION, mode: 'ordinary', configuration_digest, perspective: null, references: [] })

/** How the selector arrived. Omission and JSON null are DISTINCT submitted
 *  identities for replay, even though their first-send managed behaviour is the
 *  same: ordinary mode, perspective null, references [], and a configuration
 *  snapshot the server takes itself. Neither can ever select legacy execution
 *  -- that needs positive durable evidence against the route fence (section 2). */
export type SubmittedSelectorForm = 'omitted' | 'null' | 'explicit'
export interface SubmittedSelector {
  form: SubmittedSelectorForm
  /** present only when form is 'explicit', and still unvalidated */
  value?: unknown
}
export const submittedSelector = (envelope: Record<string, unknown>): SubmittedSelector => {
  if (!(SELECTOR_FIELD in envelope)) return { form: 'omitted' }
  const value = envelope[SELECTOR_FIELD]
  return value === null ? { form: 'null' } : { form: 'explicit', value }
}

/* ---- Refusals -------------------------------------------------------------
 * One vocabulary for the server that refuses and the composer that explains.
 * D shows an actionable message per reason and keeps the draft (section 6); A records
 * the reason with its expected/observed version basis (section 5). HTTP status uses
 * the existing conventions: 401/403 authentication/authority, 409 Brain, stale
 * or edited-version/conflicting replay, 422 invalid schema or intent (section 4). */
export const MANAGED_REFUSAL = {
  'authentication': 401,
  'authority': 403,
  'request-door-required': 422,
  'selector-schema': 422,
  'selector-too-large': 422,
  'too-many-references': 422,
  'duplicate-selection': 422,
  'invalid-unicode': 422,
  'identifier-too-long': 422,
  'context-too-large': 422,
  'text-parts-disagree': 422,
  'blank-without-content': 422,
  'selection-unavailable': 422,
  'managed-data-missing': 422,
  'retained-execution-intent': 422,
  'stale-configuration': 409,
  'brain-mismatch': 409,
  'authored-version-edited': 409,
  'replay-intent-changed': 409,
  'conflicting-association': 409,
} as const
export type ManagedRefusalReason = keyof typeof MANAGED_REFUSAL
/** The retained-content gate keeps its EXISTING refusal, unchanged and not
 *  renamed: `mentis.magnet.perspectives.require_grounded` already answers
 *  this, and section 2 requires it at request validation and again before any
 *  recovered execution while configured-source enforcement is unverified. */
export const RETAINED_GATE_CODE = 'grounded-answers-blocked'

/* ---- Canonical JSON and digests (section 3) --------------------------------------
 * Recursively sorted object keys by UNICODE SCALAR order, original array
 * order, UTF-8, no BOM or whitespace, literal Unicode, only the escaping JSON
 * requires, and no Unicode or newline normalisation. Numbers in this schema
 * are integers. The digest is SHA-256 of those bytes.
 *
 * Scalar order is why keys are not sorted with a bare `.sort()`: the default
 * compares UTF-16 code units, so an astral-plane key would sort before U+FFFD
 * in JS and after it in Python, and the two languages would publish different
 * digests for the same object. */
export type CanonicalValue = null | boolean | number | string | CanonicalValue[] | { [k: string]: CanonicalValue }

const scalars = (s: string): number[] => Array.from(s, (c) => c.codePointAt(0) as number)
const byScalarOrder = (a: string, b: string): number => {
  const x = scalars(a), y = scalars(b)
  for (let i = 0; i < Math.min(x.length, y.length); i++) if (x[i] !== y[i]) return x[i] - y[i]
  return x.length - y.length
}

/** True when every surrogate in `s` is half of a real pair. A lone surrogate
 *  has no UTF-8 encoding, so it is refused rather than canonicalised (section 3). */
export const isWellFormedUnicode = (s: string): boolean => {
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i)
    if (c >= 0xd800 && c <= 0xdbff) {
      const next = s.charCodeAt(i + 1)
      if (!(next >= 0xdc00 && next <= 0xdfff)) return false
      i++
    } else if (c >= 0xdc00 && c <= 0xdfff) return false
  }
  return true
}

/** Thrown by `canonicalJson` for a value this schema does not allow. The
 *  `reason` is a refusal reason, so a caller can answer with it directly. */
export class CanonicalError extends Error {
  readonly reason: ManagedRefusalReason
  constructor(reason: ManagedRefusalReason, words: string) { super(words); this.reason = reason }
}

/** The canonical string. Its UTF-8 encoding is the bytes that get digested.
 *  Strings go through JSON.stringify deliberately: it escapes exactly `"`,
 *  `\` and the C0 controls, with JSON's short forms, and leaves every other
 *  character literal -- which is byte-identical to Python's
 *  `json.dumps(..., ensure_ascii=False)`. The golden vectors are what proves
 *  that, rather than this comment. */
export const canonicalJson = (value: CanonicalValue): string => {
  if (value === null) return 'null'
  if (typeof value === 'boolean') return value ? 'true' : 'false'
  if (typeof value === 'number') {
    if (!Number.isSafeInteger(value)) {
      throw new CanonicalError('selector-schema', 'this schema holds integers only: ' + String(value))
    }
    return String(value)
  }
  if (typeof value === 'string') {
    if (!isWellFormedUnicode(value)) throw new CanonicalError('invalid-unicode', 'a lone surrogate has no UTF-8 encoding')
    return JSON.stringify(value)
  }
  if (Array.isArray(value)) return '[' + value.map(canonicalJson).join(',') + ']'
  if (typeof value === 'object') {
    const keys = Object.keys(value).sort(byScalarOrder)
    return '{' + keys.map((k) => canonicalJson(k) + ':' + canonicalJson(value[k])).join(',') + '}'
  }
  throw new CanonicalError('selector-schema', 'this schema holds null, booleans, integers, strings, arrays and objects only')
}

export const canonicalBytes = (value: CanonicalValue): Uint8Array => new TextEncoder().encode(canonicalJson(value))

const HEX = Array.from({ length: 256 }, (_, i) => i.toString(16).padStart(2, '0'))
export const sha256Hex = async (bytes: Uint8Array): Promise<Sha256Hex> => {
  const out = await crypto.subtle.digest('SHA-256', bytes as unknown as ArrayBuffer)
  let hex = ''
  for (const b of new Uint8Array(out)) hex += HEX[b]
  return hex
}

/** The digest of a value's canonical bytes. */
export const digestOf = async (value: CanonicalValue): Promise<Sha256Hex> => sha256Hex(canonicalBytes(value))

/** The digest of EXACT authored text: its own UTF-8 bytes, not a canonical
 *  JSON wrapping. Nothing is trimmed or normalised, so CR/LF, leading and
 *  trailing whitespace, emoji and combining characters all signify (section 3). */
export const textDigest = async (text: string): Promise<Sha256Hex> => {
  if (!isWellFormedUnicode(text)) throw new CanonicalError('invalid-unicode', 'a lone surrogate has no UTF-8 encoding')
  return sha256Hex(new TextEncoder().encode(text))
}

export const isDigestHex = (v: unknown): v is Sha256Hex =>
  typeof v === 'string' && v.length === DIGEST_HEX_CHARS && /^[0-9a-f]+$/.test(v)
export const isIdentifier = (v: unknown): v is string =>
  typeof v === 'string' && v.length > 0 && v.length <= IDENTIFIER_MAX_CHARS
  && isWellFormedUnicode(v) && /^[A-Za-z0-9][A-Za-z0-9:._-]*$/.test(v)

/* ---- Exact authored text and parts (section 3) -----------------------------------
 * `text` must equal the exact authored flow_text projection of `parts`;
 * disagreement refuses. The projection mirrors
 * `mentis.conversation.versions.flow_text` EXACTLY -- text parts and the
 * characters of inline references, in order -- because the server validates
 * with that function and the record is read back through it.
 *
 * The consequence D and A both need: a DROPPED REFERENCE CHIP produces no
 * content part and no separator text at all. Chips and typed inline references
 * become the same part types, so a chip emitted as a part would be
 * indistinguishable from authored characters and would enter flow_text as if
 * the owner had typed it. The selected object's identity travels in
 * `references` instead, where it is audited, and the chip is rendered from
 * there. Typed inline reference characters remain authored and stay in parts. */
export const AUTHORED_FLOW_PART_TYPES = ['text', 'topic', 'turn', 'conversation', 'acquired', 'object'] as const
export type AuthoredPart = { type: string; text?: string;[k: string]: unknown }

export const flowText = (parts: readonly AuthoredPart[] | null | undefined): string =>
  (parts ?? []).filter((p) => (AUTHORED_FLOW_PART_TYPES as readonly string[]).includes(p.type))
    .map((p) => p.text ?? '').join('')

/** Never trim stored input: blankness is validated separately from text, and a
 *  chip-only or file-only send is valid when a validated explicit reference or
 *  attachment supplies the content (section 3). */
export const isBlankAuthoredText = (text: string): boolean => text.trim() === ''
export const authoredTextAgrees = (text: string, parts: readonly AuthoredPart[] | null | undefined): boolean =>
  text === flowText(parts)

/** What the record keeps about the one accepted authored version. Every
 *  managed consumer -- work words, matching question, restoration block,
 *  session binding and delivery audit -- derives from THIS, never from a mix
 *  of presented and original reads (section 4). */
export interface AuthoredRevisionIdentity {
  turn: string
  revision: string
  /** canonical digest of the authored parts */
  parts_digest: Sha256Hex
  /** digest of the exact authored text's UTF-8 bytes */
  text_digest: Sha256Hex
}

/** Material means the authored text, the typed inline references or the
 *  intentional attachment parts changed, or the Turn was deleted. A
 *  metadata-only change outside those parts is not material. Any intervening
 *  material revision invalidates old-context execution even if the text is
 *  later reverted, which is why the comparison is against the recorded
 *  digests and not against the current text (section 4). */
export const materiallyRevised = (accepted: AuthoredRevisionIdentity, now: Pick<AuthoredRevisionIdentity, 'parts_digest' | 'text_digest'>): boolean =>
  accepted.parts_digest !== now.parts_digest || accepted.text_digest !== now.text_digest

/* ---- The configuration digest (section 3) ----------------------------------------
 * It covers the ENTIRE validated durable Magnet definition, not the name and
 * not the selected source ids. B exposes the one validated definition
 * snapshot and the serialisation seam used by definition writes; A must not
 * validate one read and serialise another. These two lists are what "entire"
 * means, so B's snapshot and A's digest cover the same fields. */
export const CONFIGURATION_DIGEST_INCLUDES = [
  'identity', 'name', 'source_definitions', 'source_configuration', 'source_filters',
  'collection_behavior', 'perspective_definition_refs', 'question_definition_refs', 'extensions',
] as const
export const CONFIGURATION_DIGEST_EXCLUDES = [
  'arrangement_placement', 'derived_collection_data', 'own_conversation_mirror',
] as const

/* ---- The durable snapshot (section 4) --------------------------------------------
 * Written in the SAME corpus transaction as the operation key, the
 * own-Conversation claim, the asking post, the expectations and the route. It
 * is operational provenance: not owner speech, not adopted governance, and it
 * stays out of permanent Conversation prose (sections 4 and 5). */
export interface ManagedContextSnapshot {
  managed_context_version: typeof MANAGED_CONTEXT_VERSION
  policy_version: string
  brain_instance: string
  corpus: string
  magnet: string
  definition_digest: Sha256Hex
  author: string
  observed_writer: string
  operation: string
  action: string
  route: string
  conversation: string
  submitted_form: SubmittedSelectorForm
  selections: MagnetSelectorV1 | null
  asking: AuthoredRevisionIdentity
  context_digest: Sha256Hex
}

/** The context's own digest covers its canonical body EXCLUDING that digest
 *  field -- otherwise it would have to contain itself (section 4). */
export const contextDigest = async (snapshot: Omit<ManagedContextSnapshot, 'context_digest'>): Promise<Sha256Hex> =>
  digestOf(snapshot as unknown as CanonicalValue)

/* ---- Replay (section 4) ----------------------------------------------------------
 * `posting.py`'s keyed_request whitelist needs the FULL submitted identity,
 * compared BEFORE fresh configuration or selection hydration: a routing digest
 * alone is insufficient. Same key with changed intent refuses; same key with
 * identical intent returns the first frozen result even after configuration
 * changed, creating no duplicate Turn or expectation, and never restarting
 * answered, failed, withdrawn or stopped work. */
export const KEYED_SEND_INTENT_FIELDS = [
  'text', 'parts', 'action', 'replies_to', 'addressed_to', 'recipients',
  'permissions', 'runtime', 'mode', 'origin', 'destination',
  'attachments', 'references', SELECTOR_FIELD, 'selector_form',
] as const

/* ---- Sessions and delivery (section 5) ------------------------------------------- */
/** Included in existing session freshness/binding and in BOTH the full and the
 *  continuation situation payloads. Removed, narrower or different context
 *  must obtain fresh binding or refuse; omission alone cannot clear prior
 *  native session exposure, and a version mismatch refuses even with a fresh
 *  session. No isolation claim follows from prompt wording. */
export interface SessionContextBinding {
  policy_version: string
  context_digest: Sha256Hex
  asking_turn: string
  asking_revision: string
  parts_digest: Sha256Hex
}

/** Prepared, actually supplied and refused are audited separately. `supplied`
 *  is marked only at the actual successful MARS send boundary for those bytes:
 *  a prepared snapshot, a start act or a failed send is not delivery (section 5). */
export const MANAGED_DELIVERY_STATES = ['prepared', 'supplied', 'refused', 'failed'] as const
export type ManagedDeliveryState = typeof MANAGED_DELIVERY_STATES[number]

/* ---- Validating an explicit selector (section 3) --------------------------------- */
export type SelectorCheck =
  | { ok: true; selector: MagnetSelectorV1 }
  | { ok: false; reason: ManagedRefusalReason; error: string }

const refuse = (reason: ManagedRefusalReason, error: string): SelectorCheck => ({ ok: false, reason, error })

/** Schema, bounds and shape only, and all of it before any domain write. What
 *  it deliberately does NOT do: resolve the route, read configuration, hydrate
 *  a selection or check that the selected objects exist and are reachable.
 *  Membership, kind, exact version/digest, this Magnet's recorded batch
 *  membership and the existing object/artifact gates are the server's, against
 *  the one definition snapshot, and an unavailable, deleted, unretained,
 *  restricted, corrupt or stale selection refuses there rather than being
 *  silently substituted or partially accepted. */
export const validateExplicitSelector = (value: unknown): SelectorCheck => {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    return refuse('selector-schema', 'the selector is one JSON object')
  }
  const got = value as Record<string, unknown>
  const keys = Object.keys(got).sort(byScalarOrder)
  const want = [...SELECTOR_V1_KEYS].sort(byScalarOrder)
  if (got.version !== MANAGED_CONTEXT_VERSION) {
    return refuse('selector-schema', 'unknown selector version: ' + JSON.stringify(got.version ?? null))
  }
  if (keys.length !== want.length || keys.some((k, i) => k !== want[i])) {
    return refuse('selector-schema', 'selector v1 has exactly these keys: ' + want.join(', '))
  }
  if (got.mode !== 'ordinary') return refuse('selector-schema', 'the only selector mode is ordinary')
  if (!isDigestHex(got.configuration_digest)) {
    return refuse('selector-schema', 'configuration_digest is 64 lowercase hexadecimal characters')
  }
  if (got.perspective !== null) {
    const p = got.perspective
    if (typeof p !== 'object' || p === null || Array.isArray(p)) {
      return refuse('selector-schema', 'perspective is null or one object')
    }
    const sel = p as Record<string, unknown>
    const pk = Object.keys(sel).sort(byScalarOrder)
    if (pk.length !== 3 || pk[0] !== 'id' || pk[1] !== 'question_digest' || pk[2] !== 'question_ref') {
      return refuse('selector-schema', 'perspective is exactly {id, question_ref, question_digest}')
    }
    if (!isIdentifier(sel.id) || !isIdentifier(sel.question_ref)) {
      return refuse('identifier-too-long', 'perspective id and question_ref are existing identifiers of at most ' + IDENTIFIER_MAX_CHARS + ' characters')
    }
    if (!isDigestHex(sel.question_digest)) {
      return refuse('selector-schema', 'question_digest is 64 lowercase hexadecimal characters')
    }
  }
  if (!Array.isArray(got.references)) return refuse('selector-schema', 'references is an array')
  if (got.references.length > SELECTOR_MAX_REFERENCES) {
    return refuse('too-many-references', 'at most ' + SELECTOR_MAX_REFERENCES + ' references')
  }
  const seen = new Set<string>()
  for (const r of got.references) {
    if (typeof r !== 'object' || r === null || Array.isArray(r)) {
      return refuse('selector-schema', 'each reference is one object')
    }
    const ref = r as Record<string, unknown>
    const rk = Object.keys(ref).sort(byScalarOrder)
    if (rk.length !== 4 || rk[0] !== 'digest' || rk[1] !== 'kind' || rk[2] !== 'ref' || rk[3] !== 'version') {
      return refuse('selector-schema', 'each reference is exactly {kind, ref, version, digest}')
    }
    if (!(SELECTOR_REFERENCE_KINDS as readonly unknown[]).includes(ref.kind)) {
      return refuse('selector-schema', 'reference kind is ' + SELECTOR_REFERENCE_KINDS.join(', '))
    }
    if (!isIdentifier(ref.ref)) {
      return refuse('identifier-too-long', 'reference ref is an existing identifier of at most ' + IDENTIFIER_MAX_CHARS + ' characters')
    }
    if (ref.version !== null && !isIdentifier(ref.version)) {
      return refuse('selector-schema', 'reference version is null for an immutable artifact, otherwise an identifier')
    }
    if (ref.kind === 'artifact' && ref.version !== null) {
      return refuse('selector-schema', 'an immutable artifact has version null')
    }
    if (!isDigestHex(ref.digest)) {
      return refuse('selector-schema', 'reference digest is 64 lowercase hexadecimal characters')
    }
    const key = String(ref.kind) + '\u0000' + String(ref.ref) + '\u0000' + String(ref.version)
    if (seen.has(key)) return refuse('duplicate-selection', 'the same selection appears twice')
    seen.add(key)
  }
  let bytes: Uint8Array
  try {
    bytes = canonicalBytes(got as unknown as CanonicalValue)
  } catch (e) {
    const reason = e instanceof CanonicalError ? e.reason : 'selector-schema'
    return refuse(reason, e instanceof Error ? e.message : 'the selector could not be canonicalised')
  }
  if (bytes.byteLength > SELECTOR_MAX_BYTES) {
    return refuse('selector-too-large', 'the selector is at most ' + SELECTOR_MAX_BYTES + ' canonical UTF-8 bytes')
  }
  return { ok: true, selector: got as unknown as MagnetSelectorV1 }
}
