/// <reference types="vite/client" />
/* WHICH BRAIN THIS PAGE READS, AND WHETHER IT MAY WRITE.
 *
 * Quiet Chat Mark 2 has one development server (quiet-brains.mjs, Q2_BRAINS=1)
 * in front of two Brains: the disposable development Brain, where posting
 * and the rest of Mentis's writing work as always, and DAY-TO-DAY, strictly
 * read-only -- its proxy refuses every write and never forwards it.
 *
 * The page asks which Brain it was opened on (`/__q2/brain`) before it
 * draws, then sends that Brain on every API request it makes (X-Q2-Brain),
 * so a choice made in another tab never redirects this one. Choosing the
 * other Brain reloads the page: no draft, reply or pending write is carried
 * across. Where there is no such server (a built page served by Mentis), the
 * page is whatever that server is, writable unless the older read-only
 * preview (MENTIS_READONLY) said otherwise.
 *
 * Read-only, the page offers nothing that writes: no composer, no reply, no
 * edit, no choosing or making a look, no editing instructions. */
export interface BrainChoice { brain: 'dev' | 'dayday'; label: string; readOnly: boolean }

export let READ_ONLY = import.meta.env.VITE_MENTIS_READONLY === '1'
/** the Brain chosen on the development server; null where there is none */
export let BRAIN: (BrainChoice & { choices: BrainChoice[] }) | null = null
/** the development server could not say which Brain: the page is read-only */
export let BRAIN_ERROR = false

export const READ_ONLY_WHY = 'Read-only preview: posting, replying and editing are off here.'

const API = /^\/(api|fluid\/api)(\/|$|\?)/

/** Asks which Brain this page is on; resolves once the page may draw. */
export async function loadBrain(): Promise<void> {
  let r: Response
  try { r = await fetch('/__q2/brain', { cache: 'no-store' }) } catch { BRAIN_ERROR = true; READ_ONLY = true; return }
  /* no development server (a page Mentis itself serves): the answer is its HTML */
  if (r.status === 404 || (r.ok && !(r.headers.get('content-type') ?? '').includes('json'))) return
  try {
    if (!r.ok) throw new Error(`${r.status}`)
    const b = await r.json() as BrainChoice & { choices: BrainChoice[] }
    if (b.brain !== 'dev' && b.brain !== 'dayday') throw new Error('unknown Brain')
    BRAIN = b
    READ_ONLY = b.readOnly
    /* every API request this page makes names its own Brain */
    const plain = window.fetch.bind(window)
    window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
      const url = typeof input === 'string' ? input : input instanceof URL ? input.href : input.url
      const path = url.startsWith(location.origin) ? url.slice(location.origin.length) : url
      if (!API.test(path)) return plain(input, init)
      const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined))
      headers.set('X-Q2-Brain', b.brain)
      return plain(input, { ...init, headers })
    }
  } catch {
    /* the development server answered but not with a Brain: nothing is offered that writes */
    BRAIN_ERROR = true
    READ_ONLY = true
  }
}

/** Opens the page on another Brain: the reader's explicit choice, a reload. */
export async function switchBrain(to: 'dev' | 'dayday'): Promise<void> {
  const r = await fetch('/__q2/brain', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ brain: to }) })
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`)
  /* the conversation and post addressed belong to the other Brain: start clean */
  location.assign(location.pathname)
}

/** The Brain another tab chose since this page opened, if it differs. */
export async function brainNow(): Promise<string | null> {
  try { const r = await fetch('/__q2/brain', { cache: 'no-store' }); return r.ok ? (await r.json()).brain as string : null } catch { return null }
}
