/* Fluid's HTTP client.
 *
 * Writes open a new read-sharing period before and after the request.  This
 * used to be implemented by replacing window.fetch, which made unrelated
 * code part of Fluid's state machine.  Callers now opt into the app client;
 * the browser's fetch function is never changed. */

let epoch = 0
const inFlight = new Map<string, Promise<unknown>>()
let readsOut = 0

export const readEpoch = () => epoch
export const readsInFlight = () => readsOut

/** From now on, no read joins one which began against an older record. */
export function newReadPeriod() {
  epoch++
  inFlight.clear()
}

/* OWNER AUTHENTICATION (round 3). An owner-only operation without a valid
 * owner session answers 401 `{kind: "OwnerAuthRequired", login}`; the app
 * then goes to the owner login page, which brings the owner back here.
 * Nothing else changes: the caller still sees the 401 as an error. */

/** Where to go for a response, or null: only a 401 that says
 *  `OwnerAuthRequired`, and never from the login page itself. */
export function ownerLoginTarget(status: number, body: unknown, at: { pathname: string; search: string; hash: string }): string | null {
  if (status !== 401 || !body || typeof body !== 'object' || (body as { kind?: unknown }).kind !== 'OwnerAuthRequired') return null
  if (at.pathname.startsWith('/owner/login')) return null
  return '/owner/login?next=' + encodeURIComponent(at.pathname + at.search + at.hash)
}

let leaving = false

/** Look at a response for OwnerAuthRequired and go to the login page once.
 *  Reads a clone, so the caller's body is untouched. */
export async function ownerAuthCheck(res: Response): Promise<void> {
  if (res.status !== 401 || leaving || typeof window === 'undefined') return
  const body = await res.clone().json().catch(() => null)
  const to = ownerLoginTarget(res.status, body, window.location)
  if (!to) return
  leaving = true
  window.location.assign(to)
}

export async function fluidFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? (typeof Request !== 'undefined' && input instanceof Request ? input.method : 'GET')).toUpperCase()
  if (method === 'GET' || method === 'HEAD') {
    const res = await globalThis.fetch(input, init)
    await ownerAuthCheck(res)
    return res
  }
  newReadPeriod()
  try {
    const res = await globalThis.fetch(input, init)
    await ownerAuthCheck(res)
    return res
  } finally {
    newReadPeriod()
  }
}

/** One GET in flight per URL and read period; settled answers are not cached. */
export function sharedJson<T>(url: string, headers?: HeadersInit): Promise<T> {
  const key = `${epoch} ${url}`
  const running = inFlight.get(key)
  if (running) return running as Promise<T>
  readsOut++
  const p = fluidFetch(url, { headers }).then(async (res) => {
    const body = await res.json().catch(() => null) as any
    if (!res.ok || !body || body.error) throw new Error(body?.error ?? res.statusText)
    return body as T
  }).finally(() => {
    readsOut--
    if (inFlight.get(key) === p) inFlight.delete(key)
  })
  inFlight.set(key, p)
  return p
}
