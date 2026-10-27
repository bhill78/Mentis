import { useCallback, useEffect, useMemo, useState } from 'react'
import { CLIENT_HEADERS, read } from '../api'
import { fluidFetch } from '../fluid/http'
import type { PictureTheme } from './derive'

/* ------------------------------------------------------------------------ *
 * WHERE A LOOK IS KEPT: IN THE BRAIN, BESIDE THE RECORD.
 *
 * `/api/presentation` (mentis/presentation.py) holds the looks made from a
 * picture, their pictures, and which look the brain and each Conversation
 * are drawn in -- the built-in ones included. Every device talks to the same
 * server, so a look chosen on the laptop is what the phone shows. None of it
 * is the record: nothing here is an act, and nothing an agent is given ever
 * reads it (docs/design/presentation-store.md).
 *
 * THE BROWSER KEEPS A COPY FOR READING ONLY. The last answer is kept in
 * localStorage so the canvas is drawn right away and still drawn when Mentis
 * cannot be reached. It is never written back: the server's answer replaces
 * it whenever there is one. Every change goes to the server first and the
 * screen follows what the server then says.
 *
 * ONE MOVE, ONCE. Looks made in the browser-only prototype, and atmosphere
 * choices this browser held, are carried into the brain the first time this
 * runs -- without asking, and without overwriting a choice the brain already
 * has from another device.
 * ------------------------------------------------------------------------ */

export interface SavedLook {
  id: `look-${string}`
  name: string
  created: number
  theme: PictureTheme
  pictures: { wide?: string; tall?: string }
}

export interface Choices {
  brain: string | null
  conversations: Record<string, string>
}

interface Presentation {
  version: number
  looks: SavedLook[]
  choices: Choices
}

const CACHE = 'mentis.presentation.cache.v1'
const MOVED = 'mentis.presentation.moved.v1'
/** which prototype looks have already crossed, so a move cut short never repeats one */
const MOVING = 'mentis.presentation.moving.v1'
/** where the prototype and the old atmosphere store kept things */
const OLD_LOOKS = 'mentis.pictureThemes.v1'
const OLD_CHOICES = 'mentis.atmosphere.v1'
const OLD_BRAIN = '__brain__'

const EMPTY: Presentation = { version: 1, looks: [], choices: { brain: null, conversations: {} } }

/** What a person is told when a change could not be kept. Plain words. */
export const UNREACHABLE = "Couldn't save your look — Mentis isn't reachable right now. Try again in a moment."

const pictureUrl = (sha: string) => `/api/presentation/pictures/${sha}`

/** A change of look. It carries the header the server requires of it, which a page on
 *  another site cannot send without a preflight the server refuses. */
async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fluidFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Mentis-Presentation': '1', ...CLIENT_HEADERS },
    body: JSON.stringify(body),
  })
  const out = (await res.json().catch(() => ({}))) as T & { error?: string }
  if (!res.ok || out.error) throw new Error(out.error ?? res.statusText)
  return out
}

/* ONLY WHAT HAS THE SHAPE OF A LOOK IS DRAWN. The server checks every look it
   reads and sends; this checks again, because the copy kept for reading
   offline is in localStorage, and an id or a picture name is written into a
   stylesheet. */
const LOOK_ID = /^look-[0-9a-f]{12}$/
const SHA = /^[0-9a-f]{64}$/
const drawable = (l: SavedLook) =>
  LOOK_ID.test(l?.id ?? '') &&
  !!l.theme?.wide && !!l.theme?.tall &&
  Object.values(l.pictures ?? {}).every((v) => typeof v === 'string' && SHA.test(v))
const shaped = (p: Presentation): Presentation => ({
  version: 1,
  looks: Array.isArray(p?.looks) ? p.looks.filter(drawable) : [],
  choices: {
    brain: typeof p?.choices?.brain === 'string' ? p.choices.brain : null,
    conversations:
      p?.choices?.conversations && typeof p.choices.conversations === 'object' ? p.choices.conversations : {},
  },
})

function cached(): Presentation {
  try {
    const raw = localStorage.getItem(CACHE)
    return raw ? shaped(JSON.parse(raw) as Presentation) : EMPTY
  } catch {
    return EMPTY
  }
}

async function upload(blob: Blob): Promise<string> {
  const res = await fluidFetch('/api/presentation/pictures', {
    method: 'POST',
    headers: { 'X-Mentis-Upload': '1', 'Content-Type': blob.type || 'image/jpeg' },
    body: blob,
  })
  const body = (await res.json().catch(() => ({}))) as { picture?: string; error?: string }
  if (!res.ok || !body.picture) throw new Error(body.error ?? res.statusText)
  return body.picture
}

/** A theme as the store keeps it: its pictures named by slot, not by URL. */
function forStore(t: PictureTheme): PictureTheme {
  const slot = (r: Record<string, string>, name: string) =>
    Object.fromEntries(
      Object.entries(r).map(([k, v]) => [k, k === '--canvas-image' && v !== 'none' ? `url('__${name}__')` : v]),
    )
  return { ...t, wide: slot(t.wide, 'wide'), tall: slot(t.tall, 'tall') }
}

/** A stored theme with its picture slots filled in, ready to draw. */
function withPictures(l: SavedLook): PictureTheme {
  const fill = (r: Record<string, string>) =>
    Object.fromEntries(
      Object.entries(r).map(([k, v]) => [
        k,
        v
          .replace("url('__wide__')", l.pictures.wide ? `url('${pictureUrl(l.pictures.wide)}')` : 'none')
          .replace("url('__tall__')", l.pictures.tall ? `url('${pictureUrl(l.pictures.tall)}')` : 'none'),
      ]),
    )
  return { ...l.theme, wide: fill(l.theme.wide), tall: fill(l.theme.tall) }
}

/** The CSS for one look: the same selectors atmosphere.css uses. */
export function cssFor(id: string, t: PictureTheme): string {
  const block = (r: Record<string, string>) => Object.entries(r).map(([k, v]) => `  ${k}: ${v};`).join('\n')
  return (
    `:root[data-atmosphere='${id}'] {\n${block(t.wide)}\n  color-scheme: ${t.scheme};\n}\n` +
    `:root[data-atmosphere='${id}'] .workspace.phone,\n:root[data-atmosphere='${id}'] .workspace.tablet {\n${block(t.tall)}\n}\n`
  )
}

/** Write (or clear) one <style> element by id. */
export function useStyle(id: string, css: string) {
  useEffect(() => {
    let el = document.getElementById(id) as HTMLStyleElement | null
    if (!el) {
      el = document.createElement('style')
      el.id = id
      document.head.appendChild(el)
    }
    el.textContent = css
  }, [id, css])
}

export interface PresentationStore {
  looks: SavedLook[]
  choices: Choices
  /** the last read failed: what is shown is this browser's copy */
  offline: boolean
  /** a small picture for the selector's tile */
  thumb: (id: string) => string | undefined
  save: (name: string, theme: PictureTheme, images: { wide: Blob; tall: Blob }) => Promise<SavedLook['id']>
  rename: (id: string, name: string) => Promise<void>
  remove: (id: string) => Promise<void>
  /** the look for one Conversation, or the brain when `conversation` is null;
   *  `look` null hands it back to what it inherits */
  choose: (conversation: string | null, look: string | null) => Promise<void>
}

export function usePresentation(): PresentationStore {
  const [data, setData] = useState<Presentation>(cached)
  const [offline, setOffline] = useState(false)

  const take = useCallback((got: Presentation) => {
    const p = shaped(got)
    setData(p)
    setOffline(false)
    try {
      localStorage.setItem(CACHE, JSON.stringify(p))
    } catch {
      /* a full or blocked store only costs the offline copy */
    }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const p = await read<Presentation>('/api/presentation')
      take(p)
      return p
    } catch {
      setOffline(true)
      return null
    }
  }, [take])

  // Read on arrival, and again whenever this window comes back into use --
  // which is how a change made on another device shows up here.
  useEffect(() => {
    void refresh().then((p) => p && moveOnce(p, take))
    const again = () => {
      if (document.visibilityState === 'visible') void refresh()
    }
    window.addEventListener('focus', again)
    document.addEventListener('visibilitychange', again)
    return () => {
      window.removeEventListener('focus', again)
      document.removeEventListener('visibilitychange', again)
    }
  }, [refresh, take])

  const css = data.looks.map((l) => cssFor(l.id, withPictures(l))).join('\n')
  useStyle('mentis-picture-themes', css)

  return useMemo<PresentationStore>(() => ({
    looks: data.looks,
    choices: data.choices,
    offline,
    thumb: (id) => {
      const sha = data.looks.find((x) => x.id === id)?.pictures.wide
      return sha ? pictureUrl(sha) : undefined
    },
    save: async (name, theme, images) => {
      const pictures =
        theme.backdrop === 'plain' ? {} : { wide: await upload(images.wide), tall: await upload(images.tall) }
      const out = await post<{ look: SavedLook['id']; presentation: Presentation }>('/api/presentation/looks', {
        name,
        theme: forStore(theme),
        pictures,
      })
      take(out.presentation)
      return out.look
    },
    rename: async (id, name) => {
      const out = await post<{ presentation: Presentation }>(`/api/presentation/looks/${id}`, { name })
      take(out.presentation)
    },
    remove: async (id) => {
      const out = await post<{ presentation: Presentation }>(`/api/presentation/looks/${id}`, { remove: true })
      take(out.presentation)
    },
    choose: async (conversation, look) => {
      const out = await post<{ presentation: Presentation }>('/api/presentation/choice', { conversation, look })
      take(out.presentation)
    },
  }), [data, offline, take])
}

/* -- the one move, from this browser into the brain ----------------------- */

interface OldLook {
  id: string
  name: string
  theme: PictureTheme
}

function oldBlob(key: string): Promise<Blob | undefined> {
  return new Promise((res) => {
    const r = indexedDB.open('mentis-pictures', 1)
    r.onupgradeneeded = () => r.result.createObjectStore('images')
    r.onerror = () => res(undefined)
    r.onsuccess = () => {
      try {
        const g = r.result.transaction('images').objectStore('images').get(key)
        g.onsuccess = () => res(g.result as Blob | undefined)
        g.onerror = () => res(undefined)
      } catch {
        res(undefined)
      }
    }
  })
}

let movingNow = false

async function moveOnce(p: Presentation, take: (p: Presentation) => void) {
  if (movingNow || localStorage.getItem(MOVED)) return
  movingNow = true
  let looks: OldLook[] = []
  let held: Record<string, string> = {}
  let done: Record<string, string> = {}
  try {
    looks = JSON.parse(localStorage.getItem(OLD_LOOKS) ?? '[]') as OldLook[]
    held = JSON.parse(localStorage.getItem(OLD_CHOICES) ?? '{}') as Record<string, string>
    done = JSON.parse(localStorage.getItem(MOVING) ?? '{}') as Record<string, string>
  } catch {
    /* nothing readable to move */
  }
  let latest = p
  try {
    for (const l of looks) {
      if (done[l.id]) continue
      const plain = l.theme.backdrop === 'plain'
      const [w, t] = plain ? [undefined, undefined] : await Promise.all([oldBlob(l.id + ':wide'), oldBlob(l.id + ':tall')])
      if (!plain && (!w || !t)) continue
      const pictures = plain ? {} : { wide: await upload(w!), tall: await upload(t!) }
      const out = await post<{ look: string; presentation: Presentation }>('/api/presentation/looks', {
        name: l.name,
        theme: forStore(l.theme),
        pictures,
      })
      done[l.id] = out.look
      localStorage.setItem(MOVING, JSON.stringify(done))
      latest = out.presentation
    }
    // A choice the brain already has -- from another device -- is kept.
    for (const [where, atm] of Object.entries(held)) {
      const look = atm.startsWith('pic-') ? done[atm] : atm
      if (!look || look === 'default') continue
      const conversation = where === OLD_BRAIN ? null : where
      const has = conversation === null ? latest.choices.brain : latest.choices.conversations[conversation]
      if (has) continue
      const out = await post<{ presentation: Presentation }>('/api/presentation/choice', { conversation, look })
      latest = out.presentation
    }
    localStorage.setItem(MOVED, String(Date.now()))
  } catch {
    /* Not finished this time; it carries on from where it stopped next visit. */
  } finally {
    movingNow = false
    take(latest)
  }
}
