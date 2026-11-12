/* TRACK C owns this module (package F's directory): WHAT AN ATTACHMENT IS,
   decided once, so MediaPart, the in-app viewer and the margin all agree.

   PURE. No React, no fetch, no DOM: a `Part` in, a reading out. That is what
   lets `quiet_media_unit.mjs` check the classification without a browser.

   THE SERVER'S OWN WORD DECIDES WHERE IT IS GIVEN. `treatment.view`
   (`mentis/artifacts.py` `treatment`) is read from the bytes themselves and
   is one of image | pdf | html | markdown | text | download. Where it is
   there, it is the answer.

   BUT A TURN READ DOES NOT CARRY IT, and that is worth knowing before
   reading the fallbacks below as laziness: `artifacts.part_state` describes a
   part's artifact with `verify="cached"`, and `describe` attaches `treatment`
   only when it actually read the bytes. So a part in a conversation read
   carries `state`, `size`, `name` and `claimed_media_type` and NO treatment;
   the verified word is on `/api/artifacts/<ref>?describe=1`, which is a
   second read per attachment. Fluid's own cards are in the same position and
   answer it the same way (`experimental/objectkinds.ts` reads the media type
   and the name).

   WHAT THAT MEANS FOR AN IMAGE, WHICH IS THE ONE THAT MATTERS. The server
   already decided image-ness FROM THE BYTES when the Turn was posted and
   wrote it into the part's own type (`artifacts.part`: `image` when the bytes
   are an image, `file` otherwise, "so a claim cannot make a part an image").
   So a claim never promotes a part the server called a file to an image --
   `mislabelled.txt`, claimed `image/png`, is not drawn as a picture -- and
   `isImage` is unchanged by any of this. The claim and the name decide only
   HOW A NON-IMAGE IS READ: whether a file row opens a frame, its words, or
   an offer of the bytes. Being wrong there costs a reading, not a lie: the
   frame refuses everything by policy and the download is beside it. */
import type { HeldState, Part } from '../../api'

/** How the viewer draws it. `file` is "offer the bytes, draw nothing". */
export type ViewKind = 'image' | 'video' | 'audio' | 'html' | 'markdown' | 'text' | 'file'

/** One thing the in-app viewer can show. Built from a `Part` (`itemOf`) or
 *  read back off a row's own `data-qc-*` attributes, so a part that sees only
 *  itself can still hand the viewer its post's other attachments. */
export interface ViewerItem {
  url: string
  name: string
  alt: string
  kind: ViewKind
  /** the Admission behind it, for the bounded document read; '' when unknown */
  ref: string
  /** what the sender claimed, for the row's own meta line */
  mediaType: string
  /** its size in bytes, where the record says; null where it does not */
  size: number | null
}

/** What the sender claimed these bytes are, lowercased and without parameters. */
const claimOf = (part: Part): string =>
  (part.artifact?.claimed_media_type || part.media_type || '').split(';')[0].trim().toLowerCase()

const BY_TREATMENT: Record<string, ViewKind> = {
  image: 'image', html: 'html', markdown: 'markdown', text: 'text',
  /* A PDF viewer is a program, and the server serves one as an attachment. */
  pdf: 'file',
}

/** Film and sound are never in `treatment.view` -- no signature is read for
 *  them -- so a claim is the only thing that can say so. */
function playable(claimed: string): ViewKind | undefined {
  if (claimed.startsWith('video/')) return 'video'
  if (claimed.startsWith('audio/')) return 'audio'
  return undefined
}

const TEXTUAL = new Set(['application/json', 'application/xml', 'application/x-yaml', 'application/javascript'])

/** What a claimed media type says it is. */
function claimKind(claimed: string): ViewKind | undefined {
  if (!claimed) return undefined
  if (claimed === 'text/html' || claimed === 'application/xhtml+xml') return 'html'
  if (claimed === 'text/markdown' || claimed === 'text/x-markdown') return 'markdown'
  if (claimed.startsWith('image/')) return 'image'
  if (claimed.startsWith('text/') || TEXTUAL.has(claimed)) return 'text'
  return playable(claimed)
}

const BY_EXTENSION: Record<string, ViewKind> = {
  html: 'html', htm: 'html', md: 'markdown', markdown: 'markdown',
  txt: 'text', log: 'text', json: 'text', csv: 'text', tsv: 'text',
  yml: 'text', yaml: 'text', toml: 'text', ini: 'text', diff: 'text', patch: 'text',
}

/** What the author's own filename says it is. */
function nameKind(name: string): ViewKind | undefined {
  const ext = /\.([A-Za-z0-9]{1,9})$/.exec(name)?.[1]?.toLowerCase()
  return ext ? BY_EXTENSION[ext] : undefined
}

/** How this part is drawn. */
export function viewKindOf(part: Part): ViewKind {
  const view = part.artifact?.treatment?.view
  const claimed = claimOf(part)
  if (view !== undefined) {
    const known = BY_TREATMENT[view]
    if (known) return known
    /* `download`, or a word this build does not know: the bytes carry no
       signature, so film and sound are all a claim may still decide. */
    return playable(claimed) ?? 'file'
  }
  if (part.type === 'image') return 'image'
  const guess = claimKind(claimed) ?? nameKind(part.alt || part.artifact?.name || '')
  /* A part the server called a file is never drawn as a picture on a claim:
     image-ness was decided from the bytes when the Turn was posted. */
  if (guess === 'image') return part.type === 'file' ? 'file' : 'image'
  return guess ?? 'file'
}

/** `treatment.view` is the server's own verified word for what the bytes
 *  are; a claimed media type is a fallback only when neither treatment nor
 *  part type classifies it. */
export const isImage = (part: Part): boolean => viewKindOf(part) === 'image'

/** A kind the viewer draws in place, rather than only offering. */
export const isDrawn = (kind: ViewKind): boolean => kind !== 'file'

export function formatSize(bytes: number | null | undefined): string | null {
  if (bytes == null) return null
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

/** The viewer's reading of one part. Null where there are no bytes to show. */
export function itemOf(part: Part): ViewerItem | null {
  const a = part.artifact
  if (!a?.url) return null
  const name = part.alt || a.name || part.ref || 'file'
  return {
    url: a.url,
    name,
    alt: part.alt || a.name || 'attachment',
    kind: viewKindOf(part),
    ref: a.ref || part.ref || '',
    mediaType: a.claimed_media_type || part.media_type || '',
    size: a.size ?? null,
  }
}

/** The viewer's reading of one artifact a run RETURNED -- handed over with
 *  `return_artifact`, not written into the Turn as a part. Held but no
 *  bytes to show (or not held) answers null. There is no server-verified
 *  image/file split for these the way a Turn part gets at write time
 *  (quiet2/real.ts `adapt`'s comment), so classification falls back to the
 *  same claim-or-name reading `viewKindOf` uses when a part carries no
 *  verified treatment either. */
export function returnedItemOf(a: HeldState): ViewerItem | null {
  if (a.state !== 'held' || !a.url) return null
  const claimed = (a.claimed_media_type || '').split(';')[0].trim().toLowerCase()
  const name = a.name || a.ref
  const view = a.treatment?.view
  const kind: ViewKind = view !== undefined
    ? (BY_TREATMENT[view] ?? playable(claimed) ?? 'file')
    : (claimKind(claimed) ?? nameKind(name) ?? 'file')
  return {
    url: a.url, name, alt: a.name || 'attachment', kind,
    ref: a.ref, mediaType: a.claimed_media_type || '', size: a.size ?? null,
  }
}

/** What a row says about itself under its kind: a short, plain word. */
export const kindWords: Record<ViewKind, string> = {
  image: 'image', video: 'film', audio: 'sound', html: 'html mockup',
  markdown: 'document', text: 'document', file: 'file',
}
