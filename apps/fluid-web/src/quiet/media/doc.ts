/* TRACK C owns this module: A DOCUMENT'S WORDS, BOUNDED, FOR THE VIEWER.

   ONLY WHAT IS DRAWN CROSSES THE WIRE. `/fluid/api/document?ref=` sends the
   first 256 KB and says whether there was more
   (`mentis/fluid/objects.py document_text`); `/api/artifacts/<ref>` sends the
   whole file and has no ranges, which is why opening an html mockup or a
   notes file in the viewer reads the former and offers the latter as the
   download beside it. Lifted from `fluid/workspace/ObjectBody.tsx`, which
   reads the same route the same way, without bringing Fluid's store with it:
   one read per ref while anything shows it, let go when nothing does. */
import { useEffect, useSyncExternalStore } from 'react'
import { CLIENT_HEADERS } from '../../api'
import { fluidFetch } from '../../fluid/http'

export type Doc = { text: string; cut: boolean } | { error: string }

const docs = new Map<string, Doc>()
const reading = new Map<string, AbortController>()
const heard = new Set<() => void>()
const tell = () => heard.forEach((fn) => fn())

export const documentUrl = (ref: string) => '/fluid/api/document?ref=' + encodeURIComponent(ref)

function readDoc(ref: string) {
  if (docs.has(ref) || reading.has(ref)) return
  const stop = new AbortController()
  reading.set(ref, stop)
  fluidFetch(documentUrl(ref), { headers: { ...CLIENT_HEADERS }, signal: stop.signal })
    .then(async (r) => {
      const body = await r.json().catch(() => null)
      if (!r.ok || !body || typeof body.text !== 'string')
        throw new Error(body?.why ?? body?.error ?? (r.statusText || String(r.status)))
      if (reading.get(ref) === stop) docs.set(ref, { text: body.text, cut: !!body.cut })
    })
    .catch((e: Error) => {
      if (reading.get(ref) === stop && !stop.signal.aborted) docs.set(ref, { error: e.message })
    })
    .finally(() => { if (reading.get(ref) === stop) reading.delete(ref); tell() })
}

/** This document's words while `ref` is shown; undefined until it is read. */
export function useDocument(ref: string): Doc | undefined {
  useEffect(() => {
    if (!ref) return
    readDoc(ref)
    return () => { if (!docs.has(ref)) { reading.get(ref)?.abort(); reading.delete(ref) } }
  }, [ref])
  return useSyncExternalStore(
    (fn) => { heard.add(fn); return () => { heard.delete(fn) } },
    () => (ref ? docs.get(ref) : undefined),
  )
}

/** Thrown away between suites, so one case's read is not the next's. */
export function clearDocuments() {
  for (const stop of reading.values()) stop.abort()
  reading.clear()
  docs.clear()
  tell()
}
