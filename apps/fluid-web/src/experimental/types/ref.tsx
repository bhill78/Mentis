/* EXPERIMENTAL: ONE RENDERER FOR ANY MENTIS MATERIAL, BY REFERENCE.

   reference -> provider (resolver) -> material, as the record describes it
             -> generic presentation, or a Kind-specific one if one exists
             -> host presentation: compact / expanded / pinned

   The declaration supplies only the reference(s) and a requested
   presentation. EVERYTHING ELSE IS LEARNED FROM THE RECORD at read time
   (GET /api/entries/<id>) and re-read on the shell's existing /api/pulse, so
   a pinned reference is a live view, never a copy.

   THE GENERIC CONTRACT (`Material`) IS A NORMALISATION OF WHAT MENTIS SAYS,
   NOT A SCHEMA MENTIS MUST FIT. It carries the record's own facts under their
   own names -- the Kind's declared fields, standing only where the Kind says
   standing applies, the relations that exist -- and nothing else. It never
   invents status, assignee, resolved, confidence or completion.

   SPECIALISED presentations are optional and are only presentations: they
   read the same `Material` (plus the raw record) and add no facts. Every one
   can be switched off per item, and the reference still renders generically. */
import type React from 'react'
import { useEffect, useRef, useState } from 'react'
import { GOV_HOME, readAddress, writeAddress } from '../../address'
import { useApi } from '../../api'
import { Glyph } from '../../bits'
import Pop from '../../pop'
import { Prose } from '../../prose'
import type { MenuGroup, TypeDef } from '../api'
import { turnPartScope } from '../renderable'
import { HELPER_ORIGIN, POLL_MS, allow, disallow, readOf, retry, useExternal, watch, type Read } from './external'
import './ref.css'
import { MENTIS_REF, refSpec, type Decl } from '../spec/ref'

/* ---------------------------------------------------------------- providers */

/** What a provider hands the renderer. Mentis's own record fields are kept by
    their own names in `raw`; `Material` is only what every renderer can rely on. */
export interface Material {
  provider: string
  ref: string
  /** `unconnected`: the reader has not allowed contact with the provider's backend. */
  state: 'loading' | 'resolved' | 'missing' | 'unreadable' | 'unconnected'
  why?: string
  kind: string | null
  family: string | null
  meaning: string | null
  /** The Kind's declared fields in its own order, then any recorded key it does not declare. */
  fields: { name: string; value: unknown; declared: boolean }[]
  author: string | null
  writtenBy: string | null
  at: number | null
  /** Only what the record says about standing; `applies` is the Kind's own answer (true/false/null). */
  standing: { applies: boolean | null; stands: boolean | null; establishedBy: string[]; supersededBy: string[]; deleted: boolean }
  incoming: Record<string, string[]>
  provenance: { act: string; actor: string | null; conversation: string | null }[]
  provenanceWhyNot: string | null
  versions: number
  currentVersion: string | null
  raw: Record<string, unknown> | null
}

interface Provider {
  name: string
  /** Does this provider own this form of reference? */
  claims(ref: string): boolean
  /** Resolve (a React hook: live). `via` is a grant some providers need (a
      helper session); Mentis's own provider ignores it. */
  useResolve(ref: string, via?: string): Material
}

const mentis: Provider = {
  name: 'mentis',
  claims: (r) => MENTIS_REF.test(r),
  useResolve(ref) {
    const e = useApi<Record<string, any>>(`/api/entries/${ref}`)
    return normalise(ref, e.data, e.error)
  },
}

/* The seam for later providers. ONE is registered; anything else is said to
   have no provider rather than being guessed at. */
/* THE FIRST NON-MENTIS PROVIDER (Dungeon Helper experiment). Disposable
   campaign material lives OUTSIDE the Brain, behind the helper backend, which
   serves an item only within the scope of the helper session named by `via`.
   The page never holds the corpus; a DM-only or nonexistent id get the same
   "not available". Polled every 3 s, so an edit underneath a pin shows --
   but only once the reader has connected (./external.ts): drawing a `camp:`
   reference contacts nothing, and `via=` in a block grants nothing alone. */
const campaign: Provider = {
  name: 'campaign',
  claims: (r) => /^camp:[a-z0-9-]+$/.test(r),
  useResolve(ref, via) {
    useExternal()
    useEffect(() => (via ? watch(via, ref) : undefined), [ref, via])
    return campaignMaterial(ref, readOf(via, ref))
  },
}

function campaignMaterial(ref: string, st: Read): Material {
  const base = { ...normalise(ref, null, null), provider: 'campaign' }
  if (st.st === 'no-grant') return { ...base, state: 'unreadable', why: 'no helper session grants campaign references here' }
  if (st.st === 'not-connected') return { ...base, state: 'unconnected' }
  if (st.st === 'missing') return { ...base, state: 'missing', why: `${st.err} (it does not exist, or it is outside this helper's scope)` }
  if (st.st === 'stopped') return { ...base, state: 'unreadable', why: st.err }
  if (st.st === 'loading') return base
  const d = st.data
  const f = (name: string, value: unknown) => (value === undefined || value === null || value === '' ? [] : [{ name, value, declared: true }])
  const incoming: Record<string, string[]> = {}
  for (const i of d.incoming ?? []) (incoming[i.rel] ??= []).push(`${i.from_name} (${i.from})`)
  return {
    ...base, state: 'resolved', kind: d.kind, family: 'campaign',
    meaning: 'disposable campaign material (Dungeon Helper experiment), not a Mentis record',
    fields: [
      ...f('name', d.name), ...f('also called', (d.aliases ?? []).join(', ')), ...f('summary', d.summary), ...f('details', d.details),
      ...f('DM notes', d.dm_notes), ...f('when', d.date ? `${d.date} (session ${d.session})` : null),
      ...f('stats', d.stats ? Object.entries(d.stats).map(([k, v]) => `${k} ${v}`).join(', ') : null),
      ...f('connections', (d.links ?? []).map((l: any) => `${l.rel} ${l.to_name}`).join('; ')),
    ],
    standing: { applies: false, stands: null, establishedBy: [], supersededBy: [], deleted: false },
    incoming, provenanceWhyNot: `read from the helper backend in ${d.scope} scope (requested by its helper, not authorised)`, raw: d,
  }
}

const PROVIDERS: Provider[] = [mentis, campaign]
const providerFor = (ref: string) => PROVIDERS.find((p) => p.claims(ref)) ?? null

function normalise(ref: string, d: Record<string, any> | null, error: string | null): Material {
  const empty: Material = {
    provider: 'mentis', ref, state: 'loading', kind: null, family: null, meaning: null, fields: [], author: null,
    writtenBy: null, at: null, standing: { applies: null, stands: null, establishedBy: [], supersededBy: [], deleted: false },
    incoming: {}, provenance: [], provenanceWhyNot: null, versions: 0, currentVersion: null, raw: null,
  }
  if (error && !d) return { ...empty, state: 'unreadable', why: error }
  if (!d) return empty
  if (d.missing) return { ...empty, state: 'missing', why: 'the record holds no such entry' }
  const body: Record<string, unknown> = d.body ?? {}
  // A Kind DEFINITION's `fields` describe the Kind it defines, not its own body.
  const declared: string[] = d.family === 'definition' ? [] : Array.isArray(d.fields) ? d.fields : []
  const fields = [
    ...declared.filter((f) => f in body).map((f) => ({ name: f, value: body[f], declared: true })),
    ...Object.keys(body).filter((k) => !declared.includes(k)).map((k) => ({ name: k, value: body[k], declared: false })),
  ]
  const cur = d.versions?.current
  return {
    ...empty,
    state: 'resolved',
    kind: d.kind ?? null,
    family: d.family ?? null,
    meaning: d.meaning ?? null,
    fields,
    author: d.author_alias ?? null,
    writtenBy: d.written_by ?? null,
    at: d.at ?? null,
    standing: {
      applies: d.standing_apt ?? null,
      stands: d.stands ?? null,
      establishedBy: d.established_by ?? [],
      supersededBy: d.superseded_by ?? [],
      deleted: !!d.deleted,
    },
    incoming: d.incoming ?? {},
    provenance: (d.provenance?.produced_by ?? []).map((p: any) => ({ act: p.act_type, actor: p.actor_alias, conversation: p.conversation })),
    provenanceWhyNot: d.provenance?.why_not ?? null,
    versions: d.versions?.versions?.length ?? 0,
    currentVersion: typeof cur === 'string' ? cur : cur?.id ?? null,
    raw: d,
  }
}

/* ----------------------------------------------------------- declaration */

/** SURFACE-OWNED view state. Which items are expanded, and which are shown
    generically even though a specialised presentation exists. */
interface Held { open?: Record<string, boolean>; generic?: Record<string, boolean> }

const lastRead = new Map<string, { at: number; items: unknown[] }>()

export const ref: TypeDef<Decl, Held> = {
  ...refSpec,
  slim: (a) => a.presentation !== 'expanded',
  /* One ⋯ per thing: a single reference carries the block's ⋯ on its own
     line (its item actions are added to it); untitled lists put it on a
     short lead line rather than beside the first item's own ⋯. */
  placesTools: (d, a) => d.refs.length === 1 || !a.title,
  Rich({ data, attrs, state, set, help, mode, menu, tools }) {
    const items: unknown[] = []
    useEffect(() => { lastRead.set(help.key, { at: Date.now(), items }) })
    // ONE read of recent acts for every item (observations), re-read on the pulse.
    const obs = useApi<{ operational: Act[] }>('/api/operational?newest=1&limit=400')
    menu?.([])
    const single = data.refs.length === 1
    return (
      <div className="rb-ref">
        {tools && !single && (
          <div className="rb-ref-lead">
            <span>{data.refs.length} references</span>
            <Slot tools={tools} />
          </div>
        )}
        {data.refs.map((r, i) => (
          <Item key={r.token + i} r={r} decl={data} state={state} set={set} help={help} mode={mode} title={attrs.title} into={items} acts={obs.data?.operational ?? []}
            tools={single ? tools : undefined} menu={single ? menu : undefined} />
        ))}
      </div>
    )
  },
  readable(d, a) {
    return [
      a.title ? `title: ${JSON.stringify(a.title)}` : null,
      `references (${d.refs.length}), each resolved live by Mentis when shown; nothing about the material is copied here:`,
      ...d.refs.map((r) => `- ${r.token}${r.malformed ? '   (not a readable reference)' : ''}`),
      `presentation requested: ${d.presentation}`,
    ].filter(Boolean).join('\n')
  },
  handoff(d, _a, _s, help) {
    const r = lastRead.get(help.key)
    return {
      references: d.refs.map((x) => x.token),
      as_last_read: r ? { read_at: new Date(r.at).toISOString(), note: 'a snapshot for the agent, not the material now', items: r.items } : null,
    }
  },
}

/* ----------------------------------------------------------------- items */

function openInMentis(id: string) {
  window.dispatchEvent(new CustomEvent('mentis:experimental-close-gallery'))
  window.location.hash = writeAddress({ ...readAddress(), gov: { ...GOV_HOME, filters: { ...GOV_HOME.filters }, open: [], item: id } })
}

/** Pin ONE reference on its own: the dock gets a reference, not a copy. */
export function pinOne(token: string, key: string, where: string, via?: string | null) {
  window.dispatchEvent(new CustomEvent('mentis:experimental-pin', {
    detail: { key: `${key}/pin/${token}`, where, block: { type: 'ref', info: `ref version=1 id=${token} presentation=expanded${via ? ` via=${via}` : ''}`, body: '', closed: true } },
  }))
}

const when = (t: number | null) => (t ? new Date(t * 1000).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : null)

function primary(m: Material): string {
  if (m.family === 'campaign') {
    const g = (n: string) => m.fields.find((f) => f.name === n)?.value
    return [g('name'), g('summary')].filter(Boolean).join(' — ')
  }
  const s = m.fields.find((f) => typeof f.value === 'string' && (f.value as string).trim())
  if (s) return String(s.value)
  if (m.family === 'definition') return `the Kind “${m.kind}”`
  const parts = m.fields.find((f) => Array.isArray(f.value))
  if (parts) return textOfParts(parts.value) || '(no text)'
  return '(nothing to quote)'
}

function textOfParts(v: unknown): string {
  return Array.isArray(v) ? v.map((p) => (p && typeof p === 'object' && typeof (p as any).text === 'string' ? (p as any).text : '')).join(' ').trim() : ''
}

/** Standing in the record's own words, only where the Kind says it applies. */
function standingLine(m: Material): { text: string; cls: string } | null {
  const s = m.standing
  if (s.deleted) return { text: 'Deleted: its line was ended; the record keeps it', cls: 'rb-ref-bad' }
  if (s.supersededBy.length) return { text: `Replaced by ${s.supersededBy.join(', ')}`, cls: 'rb-ref-dim' }
  if (s.applies === true) return s.stands ? { text: 'Stands (established)', cls: 'rb-ref-ok' } : { text: 'Candidate, not established', cls: 'rb-ref-dim' }
  if (s.applies === false) return null // standing is declared not meaningful for this Kind: say nothing
  return s.establishedBy.length ? { text: 'Established; this kind does not declare whether standing applies', cls: 'rb-ref-dim' } : null
}

type Act = { act: string; at: number; about: string[] }

function ItemActions({
  token,
  mode,
  provider,
  special,
  generic,
  onToggleGeneric,
  onPin,
  onOpenMentis,
}: {
  token: string
  mode: 'inline' | 'pin'
  provider: string
  special?: { name: string }
  generic: boolean
  onToggleGeneric: (generic: boolean) => void
  onPin: () => void
  onOpenMentis: () => void
}) {
  const [open, setOpen] = useState(false)
  const btnRef = useRef<HTMLButtonElement>(null)
  const wrapRef = useRef<HTMLDivElement>(null)
  const entry = useRef<'first' | 'last'>('first')
  const dismiss = () => { setOpen(false); btnRef.current?.focus() }

  useEffect(() => {
    if (!open) return
    const items = wrapRef.current?.querySelectorAll<HTMLButtonElement>('[role^="menuitem"]')
    items?.[entry.current === 'last' ? items.length - 1 : 0]?.focus()
  }, [open])

  const hasPresentation = !!special
  const hasPin = mode === 'inline'
  const hasOpenMentis = provider === 'mentis'
  if (!hasPresentation && !hasPin && !hasOpenMentis) return null

  return (
    <div ref={wrapRef} className="popwrap rb-tools-wrap">
      <button
        ref={btnRef}
        className="btn quiet glyph rb-ref-tools-btn"
        aria-label={`Actions for ${token}`}
        title="Actions"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={(e) => {
          e.stopPropagation()
          entry.current = 'first'
          if (open) dismiss(); else setOpen(true)
        }}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault()
            entry.current = e.key === 'ArrowUp' ? 'last' : 'first'
            setOpen(true)
          }
          if (e.key === 'Escape' && open) {
            e.stopPropagation()
            dismiss()
          }
        }}
      >
        <Glyph name="more" />
      </button>
      {open && (
        <>
          <div
            className="scrim"
            onClick={(e) => {
              e.stopPropagation()
              dismiss()
            }}
          />
          <Pop
            role="menu"
            aria-label={`Actions for ${token}`}
            className="rb-tools-menu"
            onKeyDown={(e) => {
              if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {
                e.preventDefault()
                e.stopPropagation()
                const items = Array.from(e.currentTarget.querySelectorAll<HTMLButtonElement>('[role^="menuitem"]'))
                const i = items.indexOf(document.activeElement as HTMLButtonElement)
                const next = e.key === 'Home' ? 0 : e.key === 'End' ? items.length - 1
                  : (i + (e.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length
                items[next]?.focus()
              }
              if (e.key === 'Tab') {
                dismiss()
              }
              if (e.key === 'Escape') {
                e.preventDefault()
                e.stopPropagation()
                dismiss()
                btnRef.current?.focus()
              }
            }}
          >
            {hasPresentation && (
              <div className="rb-tools-group" role="group" aria-label="Presentation">
                <div className="rb-tools-lbl" aria-hidden="true">Presentation</div>
                <button
                  tabIndex={-1}
                  role="menuitemradio"
                  aria-checked={!generic}
                  className={`btn quiet rb-tools-item${!generic ? ' active' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    onToggleGeneric(false)
                    dismiss()
                  }}
                >
                  <span>{special!.name}</span>
                  {!generic && <span aria-hidden="true"> ✓</span>}
                </button>
                <button
                  tabIndex={-1}
                  role="menuitemradio"
                  aria-checked={generic}
                  className={`btn quiet rb-tools-item${generic ? ' active' : ''}`}
                  onClick={(e) => {
                    e.stopPropagation()
                    onToggleGeneric(true)
                    dismiss()
                  }}
                >
                  <span>Generic</span>
                  {generic && <span aria-hidden="true"> ✓</span>}
                </button>
              </div>
            )}
            {(hasPin || hasOpenMentis) && (
              <div className="rb-tools-group" role="group" aria-label="Actions">
                <div className="rb-tools-lbl" aria-hidden="true">Actions</div>
                {hasPin && (
                  <button
                    tabIndex={-1}
                    role="menuitem"
                    className="btn quiet rb-tools-item"
                    onClick={(e) => {
                      e.stopPropagation()
                      onPin()
                      dismiss()
                    }}
                  >
                    <span>Pin</span>
                  </button>
                )}
                {hasOpenMentis && (
                  <button
                    tabIndex={-1}
                    role="menuitem"
                    className="btn quiet rb-tools-item"
                    onClick={(e) => {
                      e.stopPropagation()
                      onOpenMentis()
                      dismiss()
                    }}
                  >
                    <span>Open in Mentis</span>
                  </button>
                )}
              </div>
            )}
          </Pop>
        </>
      )}
    </div>
  )
}

/** The block's own ⋯, when the drawing places it. */
function Slot({ tools }: { tools?: React.ReactNode }) {
  return tools ? <span className="rb-tools-slot">{tools}</span> : null
}

function Item({ r, decl, state, set, help, mode, title, into, acts, tools, menu }: {
  r: { token: string; malformed: boolean }; decl: Decl; state: Held | undefined; set: (s: Held | undefined) => void
  help: { key: string; where: string }; mode: 'inline' | 'pin'; title?: string; into: unknown[]; acts: Act[]
  tools?: React.ReactNode; menu?: (g: MenuGroup[]) => void
}) {
  if (r.malformed) return <div className="rb-ref-item rb-ref-broken rb-ref-line"><span><code>{r.token}</code> — not a reference this renderer can read. Nothing was looked up.</span><Slot tools={tools} /></div>
  const p = providerFor(r.token)
  if (!p)
    return (
      <div className="rb-ref-item rb-ref-broken rb-ref-line">
        <span>
          <code>{r.token}</code> — no provider is registered for “{r.token.split(':')[0]}:” references in this experiment, so it
          cannot be resolved. (This is the seam a connector would fill.)
        </span>
        <Slot tools={tools} />
      </div>
    )
  return <Resolved token={r.token} p={p} decl={decl} state={state} set={set} help={help} mode={mode} title={title} into={into} acts={acts} tools={tools} menu={menu} />
}

/** The record's Kind in plain words: “conversation-instruction” reads “Conversation instruction”; a contribution is a Turn. */
function kindWords(m: Material): string {
  if (m.family === 'definition') return `Definition of the kind “${m.kind}”`
  if (m.kind === 'contribution' && m.family === 'entry') return 'Turn'
  const k = (m.kind ?? 'material').replace(/[-_]+/g, ' ')
  return k.charAt(0).toUpperCase() + k.slice(1)
}

function Resolved({ token, p, decl, state, set, help, mode, into, acts, tools, menu }: {
  token: string; p: Provider; decl: Decl; state: Held | undefined; set: (s: Held | undefined) => void
  help: { key: string; where: string }; mode: 'inline' | 'pin'; title?: string; into: unknown[]; acts: Act[]
  tools?: React.ReactNode; menu?: (g: MenuGroup[]) => void
}) {
  const m = p.useResolve(token, decl.via ?? undefined)
  const [reads, setReads] = useState(0)
  const seen = useRef<unknown>(null)
  useEffect(() => { if (m.raw && m.raw !== seen.current) { setReads((n) => n + 1); seen.current = m.raw } }, [m.raw])
  into.push({ ref: token, kind: m.kind, family: m.family, primary: m.state === 'resolved' ? primary(m).slice(0, 200) : null, state: m.state, standing: m.standing })

  const open = state?.open?.[token] ?? (decl.presentation === 'expanded' || mode === 'pin')
  const special = SPECIAL.find((s) => s.applies(m))
  const generic = !!state?.generic?.[token] || !special
  const toggle = (k: 'open' | 'generic', v: boolean) => set({ ...state, [k]: { ...(state?.[k] ?? {}), [token]: v } })

  // This item's own actions go into the block's ⋯ when it is the block's only item.
  if (menu) {
    const groups: MenuGroup[] = []
    if (m.state === 'resolved' && special)
      groups.push({ label: 'Presentation', items: [
        { label: special.name, checked: !generic, onSelect: () => toggle('generic', false) },
        { label: 'Generic', checked: generic, onSelect: () => toggle('generic', true) },
      ] })
    const mine: MenuGroup['items'] = []
    if (m.state === 'resolved' && mode === 'inline') mine.push({ label: 'Pin this item', onSelect: () => pinOne(token, help.key, help.where, decl.via) })
    if (m.state === 'resolved' && m.provider === 'mentis') mine.push({ label: 'Open in Mentis', onSelect: () => openInMentis(token) })
    if (mine.length) groups.push({ label: 'This item', items: mine })
    menu(groups)
  }

  const via = p.name === 'campaign' ? decl.via : null
  if (m.state === 'unconnected' && via)
    return (
      <div className="rb-ref-item rb-ref-external rb-ref-line" data-ref-link="off">
        <span>
          <code>{token}</code> — campaign material held by the Dungeon Helper experiment backend at <code>{HELPER_ORIGIN}</code>,
          outside Mentis. Not connected: nothing has been fetched. Connect allows helper session{' '}
          <code>{via.slice(0, 6)}…</code> named in this block for this tab: this and EVERY other campaign reference here naming
          that session are read, again every {POLL_MS / 1000} s, until Disconnect. That session's scope is what its helper
          requested, not an authorization, and its id is written into replies and pins, so it is not a secret.
        </span>
        <button className="btn primary" onClick={() => allow(via)}>Connect</button>
        <Slot tools={tools} />
      </div>
    )
  /* While a session is allowed, every state of a reference under it keeps the door to revoke it. */
  const revoke = via && <button className="btn quiet" title="Stop reading every campaign reference under this helper session in this tab" onClick={() => disallow(via)}>Disconnect</button>
  if (m.state === 'loading')
    return (
      <div className="rb-ref-item rb-muted rb-ref-line" data-ref-link={via ? 'loading' : undefined}>
        <span><code>{token}</code> resolving…{via && <>{' '}<span>reading from the experiment backend at <code>{HELPER_ORIGIN}</code>.</span> {revoke}</>}</span>
        <Slot tools={tools} />
      </div>
    )
  if (m.state !== 'resolved')
    return (
      <div className="rb-ref-item rb-ref-broken rb-ref-line" data-ref-link={via ? (m.state === 'missing' ? 'missing' : 'stopped') : undefined}>
        <span>
          <code>{token}</code> — {m.state === 'missing' ? (m.provider === 'mentis' ? 'Mentis holds no such entry.' : `${m.why}.`) : `could not be read: ${m.why}`}
          {via && m.state === 'missing' && (
            <> <span className="rb-muted">Asked again every {POLL_MS / 1000} s while connected, in case it appears.</span>{' '}{revoke}</>
          )}
          {via && m.state === 'unreadable' && (
            <> <span className="rb-muted">Stopped; nothing more is asked until you retry.</span>{' '}
              <button className="btn quiet" onClick={() => retry(via, token)}>Retry</button>
              {revoke}</>
          )}
        </span>
        <Slot tools={tools} />
      </div>
    )
  const st = standingLine(m)
  // FOUND IN THE COPY DRIVE: a dispute arrived (incoming `disputes`) but the
  // compact line said nothing. A dispute revokes nothing, so it is its own chip.
  const disputes = m.incoming['disputes']?.length ?? 0
  const naming = acts.filter((a) => a.about?.includes(token))
  return (
    <div className={'rb-ref-item' + (m.standing.deleted ? ' rb-ref-gone' : '')}>
      <div className="rb-ref-line">
        <span className="rb-ref-kind" title={m.meaning ?? ''}>{kindWords(m)}</span>
        <span className="rb-ref-primary">{primary(m).split('\n')[0].slice(0, open ? 400 : 140)}</span>
        {st && <span className={'rb-ref-chip ' + st.cls}>{st.text}</span>}
        {disputes > 0 && <span className="rb-ref-chip rb-ref-bad">Disputed ×{disputes} (a challenge; revokes nothing)</span>}
        <span className="rb-grow" />
        <button className="btn quiet" onClick={() => toggle('open', !open)}>{open ? 'Collapse' : 'Expand'}</button>
        {tools ? <Slot tools={tools} /> : <ItemActions
          token={token}
          mode={mode}
          provider={m.provider}
          special={special}
          generic={generic}
          onToggleGeneric={(v) => toggle('generic', v)}
          onPin={() => pinOne(token, help.key, help.where, decl.via)}
          onOpenMentis={() => openInMentis(token)}
        />}
        {revoke}
      </div>
      {open && (
        <div className="rb-ref-body">
          {generic ? <Generic m={m} /> : special!.Show({ m })}
          {/* Where it comes from, in words; the record id and how it is kept current on request. */}
          <details className="rb-disclosure rb-ref-facts">
            <summary>
              {m.provider === 'mentis' ? 'From Mentis' : 'From the Dungeon Helper backend (experiment), in this helper’s scope'}
            </summary>
            <div className="rb-disclosure-body">
              <p className="rb-tech">
                Record <code>{token}</code> via {m.provider} · read {reads} {reads === 1 ? 'time' : 'times'}
                {m.provider === 'mentis' ? ", re-read on the shell's pulse" : <>, polled every {POLL_MS / 1000} s from the experiment backend at {HELPER_ORIGIN} (outside Mentis), in the scope its helper requested</>}
              </p>
              {naming.length > 0 && <p className="rb-tech">Observed: the last act naming it was {naming[0].act} at {when(naming[0].at)}</p>}
            </div>
          </details>
        </div>
      )}
    </div>
  )
}

/* ---------------------------------------------------------------- generic */

function Value({ v }: { v: unknown }) {
  if (typeof v === 'string') return <div className="rb-ref-text">{v}</div>
  if (Array.isArray(v) && v.every((p) => p && typeof p === 'object' && 'type' in (p as object)))
    return <div className="rb-ref-text">{textOfParts(v) || <span className="rb-muted">({v.length} part{v.length === 1 ? '' : 's'} without text)</span>}</div>
  return <code className="rb-ref-json">{JSON.stringify(v)}</code>
}

/** What any record shows, derived only from what Mentis returned. */
function Generic({ m }: { m: Material }) {
  const st = m.standing
  const rel = Object.entries(m.incoming).filter(([, v]) => v.length)
  return (
    <dl className="rb-ref-dl">
      <dt>what it is</dt>
      <dd>
        {m.family === 'definition' ? `a definition of the Kind “${m.kind}”` : m.family === 'entry' ? `an entry of Kind “${m.kind}”` : `${m.family} “${m.kind}”`}
        {m.meaning && <span className="rb-muted"> — {m.meaning}</span>}
      </dd>
      {m.fields.map((f) => (
        <FieldRow key={f.name} name={f.name} declared={f.declared} v={f.value} definition={m.family === 'definition'} />
      ))}
      {m.fields.length === 0 && <><dt>content</dt><dd className="rb-muted">the record carries no body fields</dd></>}
      {/* Campaign material has no Kind definition and no standing: say nothing rather than cite one. */}
      {m.family !== 'campaign' && <><dt>standing</dt>
      <dd>
        {st.deleted ? 'deleted (its line was ended; nothing was erased)'
          : st.applies === true ? (st.stands ? `stands — established by ${st.establishedBy.join(', ')}` : 'a candidate — recorded, not established, governing nothing')
            : st.applies === false ? 'not meaningful for this Kind (its definition says so)'
              : `not declared for this Kind (unknown)${st.establishedBy.length ? `; the record does hold establishment ${st.establishedBy.join(', ')}` : ''}`}
        {st.supersededBy.length > 0 && ` · replaced by ${st.supersededBy.join(', ')}`}
        {(m.incoming['disputes']?.length ?? 0) > 0 && ` · disputed by ${m.incoming['disputes'].join(', ')} (a challenge; it revokes nothing)`}
      </dd></>}
      {rel.length > 0 && <><dt>pointed at by</dt><dd>{rel.map(([k, v]) => `${k} ×${v.length}`).join(' · ')}</dd></>}
      <dt>recorded</dt>
      <dd>
        {[m.author && `attributed to ${m.author}`, m.writtenBy && `written by ${m.writtenBy}`, when(m.at)].filter(Boolean).join(' · ') || 'no attribution recorded'}
      </dd>
      <dt>came from</dt>
      <dd>
        {m.provenance.length
          ? m.provenance.map((p) => `${p.act} by ${p.actor ?? 'somebody'}${p.conversation ? ` in ${p.conversation}` : ''}`).join('; ')
          : <span className="rb-muted">{m.provenanceWhyNot ?? 'no producing act recorded'}</span>}
      </dd>
      {(m.versions > 1 || (m.currentVersion && m.currentVersion !== m.ref)) && (
        <><dt>versions</dt><dd>{m.versions} {m.currentVersion && m.currentVersion !== m.ref ? `· current is ${m.currentVersion}` : ''}</dd></>
      )}
    </dl>
  )
}

function FieldRow({ name, declared, v, definition }: { name: string; declared: boolean; v: unknown; definition: boolean }) {
  return (
    <>
      <dt>{name}{!declared && !definition && <span className="rb-ref-undecl" title="The record holds this key; its Kind does not declare it"> (undeclared)</span>}</dt>
      <dd><Value v={v} /></dd>
    </>
  )
}

/* ------------------------------------------------------------ specialised */

/* Presentations only. Each reads the same Material and adds no facts; each
   can be switched off per item and the reference renders generically. */
const SPECIAL: { name: string; applies(m: Material): boolean; Show(p: { m: Material }): React.ReactNode }[] = [
  {
    name: 'Kind schema',
    applies: (m) => m.family === 'definition',
    Show: ({ m }) => {
      const b = (m.raw?.body ?? {}) as Record<string, unknown>
      const fields = Array.isArray(b.fields) ? (b.fields as string[]) : []
      const prop = (k: string) => (b[k] === true ? 'yes' : b[k] === false ? 'no' : 'not declared')
      return (
        <div className="rb-ref-schema">
          <p><b>The Kind “{String(b.kind ?? m.kind)}”</b> — {String(b.meaning ?? '')}</p>
          <table>
            <thead><tr><th>field an entry of this Kind may carry</th></tr></thead>
            <tbody>{fields.map((f) => <tr key={f}><td><code>{f}</code></td></tr>)}</tbody>
          </table>
          <p className="rb-muted">
            May enter Mentis already as this Kind: {prop('capturable')} · can be true or false: {prop('truth_apt')} · standing
            meaningful: {prop('standing_apt')}
          </p>
        </div>
      )
    },
  },
  {
    name: 'As the Turn reads',
    applies: (m) => m.kind === 'contribution' && m.family === 'entry',
    Show: ({ m }) => {
      const parts = (m.raw?.body as any)?.parts
      // Entries returns the retained record, not presented(current body).
      // History supplies the root Turn identity even when this is a revision,
      // but only a complete ordered line is trusted: rows numbered 1..n, this
      // record the last row and the line's current, nothing deleted. Any other
      // shape names no origin and the record is shown as source.
      const history = m.raw?.versions as { versions?: { entry?: string; version?: number; current?: boolean }[]; deleted?: unknown } | undefined
      const rows = Array.isArray(history?.versions) ? history.versions : []
      const record = m.raw?.id
      const complete = rows.length > 0 && rows.every((r, i) => r?.version === i + 1
        && typeof r.entry === 'string' && /^ent-[0-9a-f]{6,}$/.test(r.entry) && r.current === (i === rows.length - 1))
      const origin = m.provider === 'mentis' && complete && record === m.ref && m.currentVersion === record
        && rows[rows.length - 1].entry === record && !history?.deleted && !m.standing.deleted ? rows[0].entry! : null
      return (
        <blockquote className="rb-ref-turn">
          <div className="rb-muted">{m.author ?? 'somebody'} said{m.at ? `, ${when(m.at)}` : ''}:</div>
          {!origin && <p className="rb-muted">Retained record: current Turn identity/version is not established here. Marked blocks are shown as source; current Turn state is not applied.</p>}
          {Array.isArray(parts) && parts.length ? parts.map((part: any, i: number) =>
            part?.type === 'text' ? (
              <Prose key={i} src={typeof part.text === 'string' ? part.text : ''}
                scope={origin ? turnPartScope(origin, i) : `ref/${m.ref}/part/${i}`} untrusted={!origin} />
            ) : <div key={i}><Value v={part} /></div>,
          ) : <p>(no text parts)</p>}
        </blockquote>
      )
    },
  },
]
