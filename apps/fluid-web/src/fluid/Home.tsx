import { useCallback, useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from 'react'
import * as nav from './nav'
import { store, type Id } from './store'
import { PlaceRows } from './workspace/Arrange'
import { Holder, useChanged, type Arr } from './workspace/place'
import { Opt, Sec, Sheet } from './frame/Sheet'
import Tree, { type DockRule, type ZoneCtl } from './workspace/TreeView'
import { SectionChrome, t2Opener } from './surface/SurfaceChrome'
import { flickOnDrop } from './workspace/flick'
import { titleOf } from './workspace/hooks'
import { carries, dropped, hintZone, keepAsked, keepOnHome, land, objectsOfPost, useHinted, useKeepAsked, useKeeping } from './workspace/keep'
import { useScheme } from './frame/look'
import { AppearancePicker, PresentPicker, readAppearance, zoneAppearanceStyle, DEFAULT_APPEARANCE, type Appearance } from './present'
import { besideZone, canSplit, findZone, freshId, freshName, keepIn, keepShare, keepSlot, MIN_W, splitZone, unkeep, updateZone, zones, type Node, type Rect, type Slot, type Zone } from './workspace/tree'
import { sectionOf, sectionOptions, sources, type Chrome } from './sections'
import { LinkDropHost } from './conversation/linkDrop'

/* -- every collection is drawn in a zone's chrome --------------------------
 *
 * HOME IS A FLUID ARRANGEMENT (FW #189, #568 5.5): each collection is a zone
 * drawn as the workspace draws one (Zones.tsx) -- its name and count on the
 * left of the caption, its tools on the right and quiet until the zone is
 * hovered or focused (#568 5.4), its look the place's or its own, and a body
 * shown as a LIST (editorial: words and thin rules, BUG #78) or as CARDS.
 * A collection's filters are a row of words under its name that wraps and
 * never clips (#568 5.3). The collection says what it holds; the chrome
 * (HomeCell) is the same for every one.
 *
 * THE SECTIONS ARE A REGISTRY (sections/): each collection -- briefing,
 * work, needs-you, for-you, activity, and the conversation column and kept
 * zones -- is registered by the word its zone keeps (`show`), with its
 * display name, its body and the flags Home draws by. Home draws every
 * section through the registry, so a new section is added with
 * registerSection() and no edit here. */

export type HomePresent = 'list' | 'cards'

/* -- Home, an arrangement the owner shapes (Fluid completion, stream A) ---
 *
 * #188, #190: Daily Briefing, Work, Needs you, For you and Activity are
 * zones in Home's own layout, which the owner rearranges and which saves
 * like any other: split, merge, close and resize them (TreeView.tsx), choose
 * what each shows, how (a list or cards) and how it looks, use or save a
 * named layout. ONE RULE EVERYWHERE (#464): every change -- a zone, a Work
 * tab, the briefing's period, a collapsed zone -- is this tab's until Save
 * keeps it in the Brain (`/fluid/api/arrangements/home`), as a
 * conversation's arrangement is. A zone's own choices are kept, flat, in its
 * `options` (`present`, and its look as `panel`, `content`, `opacity`),
 * which is what the Brain keeps for a Home zone.
 *
 * THE CONVERSATION COLUMN IS ONE OF THEM (owner decision D1, #599): a zone
 * showing `conversation` draws the conversation column itself
 * (conversation/HomeColumn.tsx, given by the frame), placed, resized, split
 * beside, closed and saved like the rest, and in Home as it starts. Home's
 * old starter box in its toolbar went with it.
 *
 * AND WHAT IS DRAGGED OUT OF IT IS KEPT HERE (D1: drag and drop as in a
 * conversation). A zone showing `kept` keeps what is put in it, as a
 * workspace zone that keeps does (its `slot`, by live address, drawn through
 * ../present): a post dragged by its head (its words and what it carries),
 * a picture from a post, a card from another kept zone, or ◆ Keep. Let go
 * over any other Home zone, it is kept in the kept zone beside that one, or
 * in a new one split off beside it when there is none. */

/** HOME AS D1 SHAPED IT: every zone of a Home arrangement made or read since
 *  carries this in its options, so an arrangement whose owner closed the
 *  conversation column is told apart from one kept before it existed. */
const SHAPE = 2
const homeZone = (show: string, options?: Record<string, unknown>): Zone =>
  ({ type: 'zone', id: show + '-' + freshId(''), show, name: sectionOf(show)?.name ?? 'Zone', options: { ...(options ?? {}), home: SHAPE } })
const keptName = (t: Node | null) => {
  const used = new Set(t ? zones(t).map((z) => z.name) : [])
  if (!used.has('Kept')) return 'Kept'
  let i = 2
  while (used.has(`Kept ${i}`)) i++
  return `Kept ${i}`
}
const keptZone = (t: Node | null, items: string[] = []): Zone => ({ ...homeZone('kept'), name: keptName(t), slot: keepSlot(items) })

/** Home as it starts: the conversation column down its left; the briefing
 *  and Work across the rest, the other three beside one another under them. */
export function homeStart(carry: Record<string, Record<string, unknown>> = {}): Arr {
  const z = (show: string) => homeZone(show, carry[show])
  return {
    tree: { type: 'split', dir: 'row', sizes: [0.3, 0.7], kids: [
      z('conversation'),
      { type: 'split', dir: 'col', sizes: [0.28, 0.36, 0.36], kids: [
        z('briefing'), z('work'),
        { type: 'split', dir: 'row', sizes: [1 / 3, 1 / 3, 1 / 3], kids: [z('needs-you'), z('for-you'), z('activity')] },
      ] },
    ] },
    pages: [],
  }
}

/** F4 saved Home as five equal stacked zones, rebuilt on every save, never
 *  arranged by anybody: read as Home's start, with the choices it held. */
function legacy(t: Node): Record<string, Record<string, unknown>> | null {
  if (t.type !== 'split' || t.dir !== 'col' || t.kids.length !== 5) return null
  if (!t.sizes.every((x) => Math.abs(x - 0.2) < 1e-6)) return null
  const shows = t.kids.map((k) => (k.type === 'zone' ? k.show : ''))
  if (shows.join() !== 'briefing,work,needs-you,for-you,activity') return null
  return Object.fromEntries(t.kids.map((k) => [(k as Zone).show, (k as Zone).options ?? {}]))
}

/** A HOME KEPT BEFORE D1 GAINS THE COLUMN (saved, a default layout, a named
 *  one, this tab's): down its left, the rest as it was. One shaped since is
 *  left alone -- a column its owner closed stays closed. */
export function withColumn(a: Arr): Arr {
  const all = zones(a.tree)
  if (all.some((z) => z.show === 'conversation' || z.options?.home === SHAPE)) return a
  const stamp = (n: Node): Node => (n.type === 'zone' ? { ...n, options: { ...(n.options ?? {}), home: SHAPE } } : { ...n, kids: n.kids.map(stamp) })
  /* The same every time it is read, so the saved Home read this way is
     still what the Brain keeps: reading it is no change of the reader's. */
  const column: Zone = { ...homeZone('conversation'), id: 'conversation-d1' }
  return { ...a, tree: { type: 'split', dir: 'row', sizes: [0.3, 0.7], kids: [column, stamp(a.tree)] } }
}

export const home = new Holder(() => homeStart(), { migrate: withColumn, holds: 'home' })

/** A Home zone's own look, read from its options; undefined: the place's. */
const ownLook = (o: Record<string, unknown>): Partial<Appearance> | undefined =>
  o.panel || o.content || typeof o.opacity === 'number'
    ? { ...(o.panel ? { panel: o.panel as Appearance['panel'] } : {}), ...(o.content ? { content: o.content as Appearance['content'] } : {}), ...(typeof o.opacity === 'number' ? { opacity: o.opacity } : {}) }
    : undefined
const withoutLook = ({ panel: _p, content: _c, opacity: _o, ...rest }: Record<string, unknown>) => rest

/* -- keeping on Home ------------------------------------------------------- */

const titleFor = (addresses: string[], what?: string) => {
  if (what) return what
  if (addresses.length !== 1) return `${addresses.length} things`
  const st = store.objects.get(addresses[0])
  return st && 'object' in st ? titleOf(st.object) : 'it'
}
/** How wide a Home zone stays when split side by side: the conversation's
 *  stays readable (nav.READABLE), the rest are halved. */
const keepWide = (z: Zone) => (sectionOf(z.show)?.conversation ? nav.READABLE : 0)
/** MINIMIZED, THE CONVERSATION GIVES ITS ROOM BACK (adm-d0a5e868ba3d): too
 *  narrow to read, its zone is drawn as the rail -- as wide as the rail is
 *  on a conversation's page (nav.CONV_MIN) -- at the nearer edge of its row,
 *  and the zones beside it take the rest. Only drawn so: the arrangement
 *  keeps the zone where it was and its share, and saves them. */
const DOCK: DockRule = { is: (z) => !!sectionOf(z.show)?.conversation, w: nav.CONV_MIN, below: nav.READABLE }

function rectOf(zoneId: string) {
  const cell = document.querySelector(`[data-page-tree="home"] [data-zone-id="${CSS.escape(zoneId)}"]`)
  if (!cell) return undefined
  /* A zone drawn as the rail is measured as it is kept, not as drawn. */
  const b = cell.getBoundingClientRect()
  const kept = (cell as HTMLElement).dataset
  return { x: 0, y: 0, w: kept.keptW ? Number(kept.keptW) : b.width, h: kept.keptH ? Number(kept.keptH) : b.height }
}

/** Keep `addresses` in Home zone `zoneId`: in it, when it keeps; otherwise in
 *  a new kept zone split off beside it. `move`: out of the Home zone it was
 *  kept in (a kept card dragged, not copied). One step, with Undo. */
function keepOnHomeIn(addresses: string[], zoneId: string, move?: { page: string; zone: string }, what?: string, beside = false) {
  const t = home.arr.tree
  const z = findZone(t, zoneId)
  if (!z || !addresses.length) return
  const name = titleFor(addresses, what)
  const from = move && move.page === 'home' && move.zone !== zoneId ? move.zone : null
  const away = (tr: Node) => (from ? addresses.reduce((x, a) => unkeep(x, from, a), tr) : tr)
  if (sectionOf(z.show)?.kept && !beside) {
    const fresh = addresses.filter((a) => !(z.slot?.items ?? []).includes(a))
    if (!fresh.length) { nav.toast({ text: `${name} is already kept in ${z.name ?? 'that zone'}.` }); return }
    home.edit((a) => ({ ...a, tree: away(fresh.reduce((x, ad) => keepIn(x, zoneId, ad), a.tree)) }),
      `${from ? 'Moved' : 'Kept'} ${name} ${from ? 'to' : 'in'} ${z.name ?? 'the zone'}.`)
    land(zoneId, fresh[0])
    return
  }
  /* A kept zone already beside it keeps it there (opr-996398d467d1): one
     drag after another fills that zone rather than making Kept 2, Kept 3. */
  const next = !beside && besideZone(t, zoneId).find((k) => sectionOf(k.show)?.kept && k.id !== from)
  if (next) return keepOnHomeIn(addresses, next.id, move, what)
  const r = rectOf(zoneId)
  /* Beside the conversation, the conversation keeps 330 px and the new zone
     the rest (opr-dc047b8db9f4); with no room for both side by side it goes
     under it, as for any zone too narrow, and with no room there either it
     is not made: never the conversation halved down to its rail. */
  const keep = keepWide(z)
  if (keep && r && !canSplit(r, 'row', keep) && !canSplit(r, 'col')) {
    nav.toast({ text: `No room for a new zone beside ${z.name ?? 'the conversation'}: it keeps ${keep} px to stay readable, and a new zone needs ${MIN_W} more. Keep ${name} in a kept zone, or widen this one.` })
    return
  }
  const dir = canSplit(r, 'row', keep) || !canSplit(r, 'col') ? 'row' : 'col'
  const made = keptZone(t, addresses)
  const share = dir === 'row' && r ? keepShare(r.w, keep) : 0.5
  home.edit((a) => ({ ...a, tree: away(splitZone(a.tree, zoneId, dir, made, false, share).tree) }),
    `Kept ${name} in ${made.name}, beside ${z.name ?? 'the zone'}: it keeps what you put there.`)
  land(made.id, addresses[0])
}

/** A post dropped on a Home zone: what it is made of, kept in one step. */
async function keepPostOnHome(post: Id, zoneId: string) {
  const all = await objectsOfPost(post)
  const n = store.posts.get(post)?.number
  const what = n != null ? `#${n}` : 'the post'
  if (!all.length) { nav.toast({ text: `${what} has nothing to keep yet.` }); return }
  keepOnHomeIn(all, zoneId, undefined, what)
}

/** Keep's choices on Home (◆ on a post in Home's column, or on a kept card):
 *  Home's kept zones, or a new one beside the zone it came from. */
function HomeKeepChooser() {
  const ask = useKeepAsked()
  const arr = useSyncExternalStore(home.subscribe, home.snapshot)
  useEffect(() => keepOnHome((addresses, zone, move) => keepOnHomeIn(addresses, zone, move)), [])
  if (!ask) return null
  const { item } = ask
  const all = zones(arr.tree)
  const fromZone = item.zone ? all.find((z) => z.id === item.zone) : undefined
  const kept = all.filter((z) => sectionOf(z.show)?.kept && z.id !== item.zone)
  const beside = fromZone ?? all.find((z) => sectionOf(z.show)?.conversation) ?? all[all.length - 1]
  const move = item.kept && item.zone ? { page: 'home', zone: item.zone } : undefined
  const pick = (fn: () => void) => () => { keepAsked(); fn() }
  const lit = (id: string) => (on: boolean) => hintZone(on ? id : null)
  return (
    <Sheet anchor={ask.anchor} onClose={keepAsked} label="keep">
      <Sec>Keep {titleFor([item.address])}</Sec>
      {kept.map((z) => (
        <Opt key={z.id} onHover={lit(z.id)} onPick={pick(() => keepOnHomeIn([item.address], z.id, move))}>
          {move ? 'Move to' : 'In'} {z.name ?? 'Kept'}{z.slot?.items.includes(item.address) ? ' (already there)' : ''}
        </Opt>
      ))}
      {beside && (
        <Opt onHover={lit(beside.id)} onPick={pick(() => keepOnHomeIn([item.address], beside.id, move, undefined, true))}>
          In a new zone beside {beside.name ?? 'this one'}
        </Opt>
      )}
    </Sheet>
  )
}

/* A FOLDED ZONE GIVES ITS SPACE BACK (#568 5.2, opr-a1deafdeab22): it is
   laid out at its caption's height, and the zones above and below it take
   the rest. Its share is kept for when it opens. A zone still asking what
   to show needs only its caption and its choices: beside a folded one, the
   row they share is no taller than that. */
const FOLDED_H = 40
const CHOICE_W = 116
const CHOICE_H = 34
const foldedTo = (z: Zone, w: number): number | null => {
  const def = sectionOf(z.show)
  if (def?.conversation) return null
  if (z.options?.collapsed && def) return FOLDED_H
  if (z.show !== 'choose') return null
  const rows = Math.max(1, Math.ceil((sources('home').length * CHOICE_W) / Math.max(CHOICE_W, w - 28)))
  return FOLDED_H + 24 + rows * CHOICE_H + 16
}

/** What the frame draws in the zone that shows the conversation: `widen`
 *  makes the zone that wide, from the zones beside it (ZoneCtl.widen);
 *  `across`, it is as wide as Home (ZoneCtl.across); `railTools`, the zone's
 *  tools drawn as the rail (no split). */
export type ConversationSlot = (p: { px: number; tools: ReactNode; railTools: ReactNode; widen: (px: number) => boolean; across: boolean }) => ReactNode

function HomeCell({ z, r, ctl, onOpenPost, onOpenGovernance, setOptions, setShow, setSlot, placeLook, conversation, columnElsewhere }: {
  z: Zone; r: Rect; ctl: ZoneCtl; onOpenPost: (c: Id, p: Id, decision?: Id) => void
  /** the Governance page, reached from Needs you */
  onOpenGovernance?: () => void
  setOptions: (o: Record<string, unknown>) => void; setShow: (show: string) => void
  setSlot: (f: (s: Slot) => Slot, words?: string) => void
  /** Home's own look (Arrange: Look for every zone here), which a zone shows unless it has its own */
  placeLook: Appearance
  conversation?: ConversationSlot
  /** another zone already shows the conversation column */
  columnElsewhere: boolean
}) {
  const [menuAt, setMenuAt] = useState<HTMLElement | null>(null)
  const close = useCallback(() => setMenuAt(null), [])
  const cap = useRef<HTMLDivElement | null>(null)
  const [over, setOver] = useState(false)
  const keeping = useKeeping()
  const hinted = useHinted() === z.id
  const scheme = useScheme()
  const o = z.options ?? {}
  const collapsed = !!o.collapsed
  const def = sectionOf(z.show)
  const isKept = !!def?.kept
  const present: HomePresent = o.present === 'cards' ? 'cards' : 'list'
  const own = ownLook(o)
  const appearance = readAppearance(own, placeLook)
  const look: { className: string; style: CSSProperties } = zoneAppearanceStyle(appearance, scheme)
  const toggle = () => setOptions({ ...o, collapsed: !collapsed })
  /* A zone still asking what to show keeps the name it was made with (a
     Home saved with "Stage" comes back as Stage); it asks in its body. */
  const name = isKept ? z.name ?? def?.name ?? 'Kept' : def?.name ?? z.name ?? 'Choose what it shows'
  const offered = sources('home').filter((s) => !s.conversation || !columnElsewhere || s.show === z.show)

  /* THE CONVERSATION COLUMN, in this zone: the column's own quiet tools
     carry the zone's (split, merge, close); its width is the zone's. */
  if (def?.conversation)
    return (
      <div className="fw-home-cell fw-home-conv" data-zone="conversation">
        {conversation?.({ px: r.w, widen: ctl.widen, across: ctl.across,
          tools: <SectionChrome id={z.id} name={name} ctl={ctl} kind="conversation" title={null} />,
          railTools: <SectionChrome id={z.id} name={name} ctl={ctl} kind="conversation" title={null} level="icon" also={{ arrange: false }} /> })}
      </div>
    )

  const sheet = menuAt && (
    <Sheet anchor={menuAt} onClose={close} label={`${name} zone`}>
      {/* Grouped as a workspace section's menu is: what the zone brings in,
          then how it looks; arranging it stays last. */}
      <Sec>Brings in</Sec>
      {offered.map((s) => <Opt key={s.show} on={z.show === s.show} onPick={() => { close(); setShow(s.show) }}>{s.name}</Opt>)}
      {def && (
        <>
          <Sec>Look</Sec>
          {isKept
            ? <PresentPicker mode={(z.slot ?? keepSlot()).present} onMode={(m) => setSlot((s) => ({ ...s, present: m }))} />
            : (
              <>
                <Sec>Show as</Sec>
                <Opt on={present === 'list'} onPick={() => setOptions({ ...o, present: 'list' })}>A list</Opt>
                <Opt on={present === 'cards'} onPick={() => setOptions({ ...o, present: 'cards' })}>Cards</Opt>
              </>
            )}
          <AppearancePicker value={appearance}
            onChange={(a) => setOptions({ ...o, panel: a.panel, content: a.content, opacity: a.opacity })}
            onReset={() => setOptions(withoutLook(o))}
            isDefault={!own} resetLabel={["Back to Home's look", "Home's look"]} />
        </>
      )}
      <Sec>Arrange</Sec>
      <Opt off={!ctl.canSplitRow} why={ctl.whyNoSplitRow} onPick={() => { close(); ctl.split('row') }}>Split side by side</Opt>
      <Opt off={!ctl.canSplitCol} why={ctl.whyNoSplitCol} onPick={() => { close(); ctl.split('col') }}>Split top and bottom</Opt>
      <Opt off={!ctl.canMerge} onPick={() => { close(); ctl.merge() }}>Merge with the zone beside it</Opt>
      <Opt off={!ctl.canClose} onPick={() => { close(); ctl.close() }}>Close this zone</Opt>
      {isKept && !!z.slot?.items.length && (
        <Opt onPick={() => { close(); setSlot((s) => ({ ...s, items: [] }), `${name} keeps nothing now.`) }}>Stop keeping what is here ({z.slot.items.length})</Opt>
      )}
    </Sheet>
  )
  /* The chrome every collection is drawn in: name and count on the left;
     fold, the zone's tools and ⋯ on the right, quiet until hovered. */
  const chrome: Chrome = ({ count, filters, tools, children }) => (
    <>
      <div className="wk-zcap fw-home-cap" ref={cap}>
        <SectionChrome id={z.id} name={name} ctl={ctl}
          title={<span className="wk-what fw-zone-title">{isKept && <span className="wk-keptmark" aria-hidden="true">{'◆'}</span>}{name}</span>}
          extra={<>{count ? <span className="fw-zone-count">{count}</span> : null}{tools}</>}
          also={{ fold: def ? { on: collapsed, run: toggle } : undefined, settings: () => setMenuAt(t2Opener(cap.current)) }} />
      </div>
      {!collapsed && filters}
      {!collapsed && <div className={'wk-zbody fw-home-body fw-as-' + (isKept ? 'kept' : present)}>{children}</div>}
    </>
  )
  let body: ReactNode
  if (def?.body)
    body = (
      <def.body z={z} options={sectionOptions(def, o)} setOption={(key, value) => setOptions({ ...o, [key]: value })}
        setSlot={setSlot} onOpenPost={onOpenPost} onOpenGovernance={onOpenGovernance} chrome={chrome} />
    )
  else
    body = chrome({
      children: (
        <div className="fw-choose" role="group" aria-label={`Choose what ${name} shows`}>
          {z.name && <span className="fw-choose-ask">Choose what it shows</span>}
          {offered.map((s) => <button key={s.show} className="fw-tab" data-show={s.show} onClick={() => setShow(s.show)}>{s.name}</button>)}
        </div>
      ),
    })
  /* Something dragged out of a post or a kept zone, let go here: kept. */
  const onDrop = (e: React.DragEvent) => {
    setOver(false)
    if (flickOnDrop(e, z.id)) { e.preventDefault(); return }
    const got = dropped(e)
    if (!got) return
    e.preventDefault()
    if ('post' in got) { void keepPostOnHome(got.post, z.id); return }
    const it = got.item
    if (it.zone === z.id && it.page === 'home') return
    keepOnHomeIn([it.address], z.id, it.kept && it.zone && it.page && !e.ctrlKey ? { page: it.page, zone: it.zone } : undefined)
  }
  return (
    <div className={'fw-home-cell' + (collapsed ? ' fw-collapsed' : '')}>
      <section className={'wk-zone wk-panel fw-home-zone fw-zone-' + (def ? z.show : 'choose') + ' ' + look.className
        + (over || hinted ? ' wk-drop' : '') + (keeping && isKept ? ' wk-target' : '')}
        style={look.style} data-zone={def ? z.show : 'choose'} data-present={isKept ? (z.slot ?? keepSlot()).present : present} data-look={own ? 'own' : 'place'}
        aria-label={def ? name.toLowerCase() : 'new zone'}
        onDragOver={(e) => { if (!carries(e)) return; e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; if (!over) setOver(true) }}
        onDragLeave={(e) => { if (!e.currentTarget.contains(e.relatedTarget as globalThis.Node | null)) setOver(false) }}
        onDrop={onDrop}>
        {body}
      </section>
      {sheet}
    </div>
  )
}

export default function Home({
  onOpenPost,
  onOpenGovernance,
  conversation,
}: {
  onOpenPost: (conversationId: Id, postId: Id, decision?: Id) => void
  /** the Governance page, reached from Needs you */
  onOpenGovernance?: () => void
  /** the conversation column, drawn in the zone that shows it (D1) */
  conversation?: ConversationSlot
}) {
  const arr = useSyncExternalStore(home.subscribe, home.snapshot)
  const changed = useChanged(home)
  const placeLook = readAppearance(arr.appearance, DEFAULT_APPEARANCE)
  const [arrangeAt, setArrangeAt] = useState<HTMLElement | null>(null)
  const closeArrange = useCallback(() => setArrangeAt(null), [])
  useEffect(() => { home.enter('home', 'home') }, [])
  /* F4's five equal zones read as Home's start, carrying their choices. */
  useEffect(() => {
    const carry = home.from === 'saved' ? legacy(arr.tree) : null
    if (carry) home.quiet(() => homeStart(carry))
  }, [arr])
  const edit = (id: string, f: (z: Zone) => Zone, words?: string) =>
    words ? home.edit((a) => ({ ...a, tree: updateZone(a.tree, id, f) }), words) : home.quiet((a) => ({ ...a, tree: updateZone(a.tree, id, f) }))
  const shown = zones(arr.tree)
  return (
    <div className="fw-home fw-home-tree" aria-label="home" data-look="">
      <div className="fw-home-bar">
        <button className="fw-home-arrange" aria-expanded={!!arrangeAt} data-changed={changed ? '' : undefined}
          title={changed ? 'Home is changed in this tab: Save keeps it in the Brain' : undefined}
          onClick={(e) => setArrangeAt(e.currentTarget)}>Arrange{changed && <span className="fw-changed" aria-label="(changed, not saved)"> ●</span>} ▾</button>
        {arrangeAt && <Sheet anchor={arrangeAt} onClose={closeArrange} label="arrange home"><PlaceRows h={home} onClose={closeArrange} kind="home" /></Sheet>}
      </div>
      <div className="fw-home-arrangement wk wk-home">
        <Tree tree={arr.tree} label="Home" page="home" folded={foldedTo} wrap keepWide={keepWide} dock={DOCK}
          onEdit={(f, words) => home.edit((a) => ({ ...a, tree: f(a.tree) }), words)}
          onLive={(t, done) => home.live({ ...home.arr, tree: t }, done ? { from: { ...home.arr, tree: done.from } } : undefined)}
          made={(t) => ({ ...homeZone('choose'), name: freshName(t) })}
          renderZone={(z, r, ctl) => (
            <HomeCell z={z} r={r} ctl={ctl} onOpenPost={onOpenPost} onOpenGovernance={onOpenGovernance} placeLook={placeLook} conversation={conversation}
              columnElsewhere={shown.some((x) => sectionOf(x.show)?.conversation && x.id !== z.id)}
              setOptions={(options) => edit(z.id, (x) => ({ ...x, options }))}
              setSlot={(f, words) => edit(z.id, (x) => ({ ...x, slot: f(x.slot ?? keepSlot()) }), words)}
              setShow={(show) => edit(z.id, (x) => {
                const to = sectionOf(show)
                return {
                  ...x, show,
                  name: to?.kept ? (sectionOf(x.show)?.kept ? x.name : keptName(home.arr.tree)) : to?.name ?? x.name,
                  ...(to?.kept && !x.slot ? { slot: keepSlot() } : {}),
                }
              })} />
          )} />
      </div>
      <HomeKeepChooser />
      <LinkDropHost />
    </div>
  )
}
