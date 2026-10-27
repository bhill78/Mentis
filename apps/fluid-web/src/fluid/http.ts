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

export async function fluidFetch(input: RequestInfo | URL, init?: RequestInit): Promise<Response> {
  const method = (init?.method ?? (typeof Request !== 'undefined' && input instanceof Request ? input.method : 'GET')).toUpperCase()
  if (method === 'GET' || method === 'HEAD') return globalThis.fetch(input, init)
  newReadPeriod()
  try {
    return await globalThis.fetch(input, init)
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
