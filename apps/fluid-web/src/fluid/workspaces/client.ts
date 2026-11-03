/* A WORKSPACE'S DOORS, TYPED (docs/magnets/M1-contract.md, "A workspace's doors"
 * and "Where an agent request goes"). Every call is one door, and each refusal
 * keeps which it was: nothing here retries, guesses or falls back.
 *
 * What a workspace holds is a curated list of REFERENCES. This client carries
 * them as they were kept, unknown fields too, and never reads what one refers
 * to: `curated: true` says somebody chose it, not that it is so. Whether a
 * request may reach an object is Mentis's to say when it is asked. */

import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../http'
import { newOp, type Id } from '../store'

export type WorkspaceId = string
export type ObjectId = string

export const OBJECT_KINDS = ['magnet', 'conversation', 'chat', 'file', 'image', 'evidence', 'report', 'participant', 'other'] as const
export type ObjectKind = (typeof OBJECT_KINDS)[number] | (string & {})

const WORKSPACE_ID = /^wsp-[a-z0-9_-]{1,60}$/
/** Is this key a workspace's, not a Conversation's? */
export const isWorkspaceId = (v: unknown): v is WorkspaceId => typeof v === 'string' && WORKSPACE_ID.test(v)

export interface ObjectSource { kind: ObjectKind; ref: string }
export interface Provenance { source: ObjectSource; brain?: string; by?: Id; at?: number; [more: string]: unknown }
export interface WorkspaceObject {
  id: ObjectId
  kind: ObjectKind
  ref: string
  curated: boolean
  provenance: Provenance
  observed?: { version?: string; at?: number }
  [more: string]: unknown
}
export interface Manifest {
  id: WorkspaceId
  name: string
  revision: number
  created: number
  updated: number
  /** the workspace's own Conversation, absent until a request first needs it */
  conversation?: Id
  objects: WorkspaceObject[]
  [more: string]: unknown
}
/** In brief, as listed; one that cannot be read says why instead. */
export type WorkspaceBrief =
  | { id: WorkspaceId; name: string; objects: number; revision: number; updated: number; unreadable?: undefined }
  | { id: WorkspaceId; unreadable: string; name?: undefined }
export interface WorkspaceAnswer { id: WorkspaceId; manifest: Manifest; changed?: boolean; replayed?: boolean; object?: WorkspaceObject }

/** What to add: the door gives it its id and marks it curated. */
export interface NewObject { kind: ObjectKind; ref: string; provenance: Provenance; observed?: WorkspaceObject['observed'] }
export type Seed = { magnet: string } | { conversation: Id }
export type Destination = { conversation: Id } | { magnet: string }

/* -- why not -------------------------------------------------------------------- */

export type RefusalKind =
  | 'missing'     // 404: no such workspace
  | 'gone'        // 410: it was deleted
  | 'unreadable'  // 409: its file cannot be read, and is left as it is
  | 'conflict'    // 422: this operation key was used for a different request
  | 'declined'    // 422: refused for what the request names (a Magnet that isn't there)
  | 'malformed'   // 400: malformed or over a bound
  | 'lost'        // no answer: the request may or may not have been taken

const SAID: Record<RefusalKind, string> = {
  missing: 'This workspace isn’t there.',
  gone: 'This workspace was deleted.',
  unreadable: 'This workspace can’t be read, and was left as it is.',
  conflict: 'That operation key was already used for a different request, so nothing was written.',
  declined: 'Mentis refused this.',
  malformed: 'Mentis refused this as malformed or over a limit.',
  lost: 'No answer came back. It may or may not have been done: trying again is the same request.',
}

export class WorkspaceRefusal extends Error {
  readonly refusal: RefusalKind
  readonly status: number | null
  /** the server's own words, as they were said */
  readonly said: string | null
  constructor(refusal: RefusalKind, status: number | null, said: string | null) {
    super(said && said !== SAID[refusal] ? `${SAID[refusal]} ${said}` : SAID[refusal])
    this.refusal = refusal
    this.status = status
    this.said = said
  }
}

/** Which refusal an answer is. A 422 is a key's conflict only where it says so:
 *  a Magnet that isn't there is also a 422, and it is another thing to be told. */
export function refusalOf(status: number, body: { error?: unknown; kind?: unknown; first?: unknown } | null): WorkspaceRefusal {
  const said = typeof body?.error === 'string' ? body.error : null
  const kind: RefusalKind = status === 404 ? 'missing' : status === 410 ? 'gone' : status === 409 ? 'unreadable'
    : status === 422 ? (body?.kind === 'Conflict' || body?.first ? 'conflict' : 'declined')
    : status >= 400 && status < 500 ? 'malformed' : 'lost'
  return new WorkspaceRefusal(kind, status, said)
}

async function door<T>(path: string, body?: unknown): Promise<T> {
  let res: Response
  try {
    res = await fluidFetch('/fluid/api/' + path, body === undefined
      ? { headers: { ...CLIENT_HEADERS } }
      : { method: 'POST', headers: { ...CLIENT_HEADERS, 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  } catch {
    throw new WorkspaceRefusal('lost', null, null)
  }
  const got = await res.json().catch(() => null)
  if (!res.ok || !got || got.error) throw refusalOf(res.status, got)
  return got as T
}

/* -- one operation key per occurrence ------------------------------------------- */

const held = new Map<string, string>()
/** A retry after a lost answer is the same operation, under the same key. Once
 *  Mentis has answered, however it answered, the occurrence is over and the next
 *  one has its own: a key refused is never sent again. */
export async function once<T>(sig: string, act: (op: string) => Promise<T>): Promise<T> {
  const op = held.get(sig) ?? newOp()
  held.set(sig, op)
  try {
    const out = await act(op)
    held.delete(sig)
    return out
  } catch (e) {
    if (!(e instanceof WorkspaceRefusal) || e.refusal !== 'lost') held.delete(sig)
    throw e
  }
}
const write = (path: string, body: Record<string, unknown>) =>
  once(JSON.stringify([path, body]), (op) => door<WorkspaceAnswer>(path, { ...body, op }))
const at = (id: WorkspaceId) => `workspaces/${encodeURIComponent(id)}`

/* -- the doors ------------------------------------------------------------------ */

export const listWorkspaces = () => door<{ workspaces: WorkspaceBrief[] }>('workspaces').then((r) => r.workspaces)
export const readWorkspace = (id: WorkspaceId) => door<{ id: WorkspaceId; manifest: Manifest }>(at(id))
/** Blank with neither; with `from`, one curated object first, whose provenance
 *  the door writes. A workspace's id is minted by the door, never here. */
export const createWorkspace = (o: { name?: string; from?: Seed } = {}) =>
  write('workspaces', { ...(o.name ? { name: o.name } : {}), ...(o.from ? { from: o.from } : {}) })
export const renameWorkspace = (id: WorkspaceId, name: string) => write(`${at(id)}/rename`, { name })
export const addObject = (id: WorkspaceId, object: NewObject) => write(`${at(id)}/objects`, { object })
export const removeObject = (id: WorkspaceId, oid: ObjectId) => write(`${at(id)}/objects/${encodeURIComponent(oid)}/remove`, {})
export const reorderObjects = (id: WorkspaceId, order: ObjectId[]) => write(`${at(id)}/reorder`, { order })

/* -- a request started from a workspace ----------------------------------------- */

export interface Route { rule: string; conversation: Id; created: boolean }
export interface RequestAnswer { post: Id; replayed?: boolean; route: Route; [more: string]: unknown }

/** What a result can be named to go to: a Magnet or a Conversation the workspace holds now. */
export const destinationOptions = (objects: readonly WorkspaceObject[]) => objects.filter((o) => o.kind === 'magnet' || o.kind === 'conversation')
export const destinationValue = (o: WorkspaceObject) => `${o.kind}:${o.ref}`
/** The destination chosen, while it is still offered; otherwise none, which is the
 *  workspace's own Conversation. What is shown and what is sent both read this. */
export const destinationHeld = (chosen: string, objects: readonly WorkspaceObject[]) =>
  destinationOptions(objects).some((o) => destinationValue(o) === chosen) ? chosen : ''
export const destinationOf = (v: string): Destination | null => {
  const at = v.indexOf(':')
  if (at < 0) return null
  const kind = v.slice(0, at), ref = v.slice(at + 1)
  return kind === 'magnet' ? { magnet: ref } : kind === 'conversation' ? { conversation: ref } : null
}

/** `POST /fluid/api/requests`' body: the post as the composer built it, with
 *  `from` where it was started in place of `conversation`. `objects`, in the order
 *  asked, is left out for the whole workspace; `destination` is left out for the
 *  workspace's own Conversation. Nothing here reads which objects these are to
 *  choose where it goes, so no Magnet is primary, however many are selected. */
export function workspaceRequest(post: Record<string, unknown>, workspace: WorkspaceId, op: string,
  { objects = [], destination = null }: { objects?: readonly ObjectId[]; destination?: Destination | null } = {}): Record<string, unknown> {
  const { conversation: _conversation, replies_to: _replies, ...said } = post
  return { ...said, from: { workspace }, ...(objects.length ? { objects: [...objects] } : {}), ...(destination ? { destination } : {}), op }
}
export const sendRequest = (body: Record<string, unknown>) => door<RequestAnswer>('requests', body)
