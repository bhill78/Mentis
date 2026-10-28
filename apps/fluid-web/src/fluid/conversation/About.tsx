/* ABOUT THIS CONVERSATION: Brief, Actions, Follow ups, Media and Guidance as
 * one slide-out beside it (#188's capability table: "zone kinds or
 * slide-outs; no header strip"), opened from the conversation's menu.
 *
 * The five views are registered sections (sections/conversationViews.tsx,
 * scope 'conversation'): this slide-out draws the very same bodies a
 * workspace section brings in as its feed, with the same data and the same
 * useFacts -- nothing is implemented twice. KEEP AS SECTION keeps the view
 * shown as a section beside the conversation's primary
 * (workspace/feedSection.ts); it belongs to the conversation's workspace,
 * so on Home -- where that is not shown -- it is not offered. Every row
 * goes to its post; nothing here writes. */

import { useEffect } from 'react'
import * as nav from '../nav'
import { store, type Id } from '../store'
import { refreshFacts, useFacts } from './facts'
import { useConversation, useNav } from './hooks'
import { sectionOf, sectionOptions, type Chrome } from '../sections'
import { keepFeedSection } from '../workspace/feedSection'
import type { Slot, Zone } from '../workspace/tree'

const SECTIONS: [nav.AboutSection, string][] = [
  ['brief', 'Brief'], ['actions', 'Actions'], ['followups', 'Follow ups'], ['media', 'Media'], ['guidance', 'Guidance'],
]

/** Go to a post in this conversation: read it (loading it first if needed). */
function goTo(conversation: Id, post: Id) {
  const go = () => nav.read(conversation, post, store.posts.get(post)?.number ?? null)
  if (store.posts.has(post)) go()
  else void store.loadPosts([post]).then(go)
}

/* The slide-out draws a view as the body it is, with no zone or slot of its
   own: the zone record it asks for is this one, the chrome its body calls
   renders only the children (the sheet has the caption), and there is
   nothing to keep an option in. */
const ABOUT_ZONE: Zone = { type: 'zone', id: 'about', show: 'objects' }
const asIs: Chrome = ({ children }) => <>{children}</>
const noKeep = () => {}
const noSlot = (_f: (s: Slot) => Slot, _words?: string) => {}

export default function About({ conversation, section }: { conversation: Id; section: nav.AboutSection }) {
  const conv = useConversation(conversation)
  const facts = useFacts(conversation)
  const s = useNav()
  useEffect(() => { refreshFacts(conversation) }, [conversation])
  const open = (s: nav.AboutSection) =>
    nav.openDetail({ kind: 'about', conversation, section: s, anchor: { kind: 'zone', zone: 'conversation' }, mode: 'aside' })
  const def = sectionOf(section)
  const name = def?.name ?? 'This view'
  return (
    <aside className="fw-thread fx-sheet fx-about" aria-label="about this conversation">
      <header className="fx-sheet-head fw-thread-head">
        <button className="fx-ret" data-act="back" title="Back to the conversation" onClick={() => nav.closeAll()}>‹ Conversation</button>
        <h3>About {conv?.name ?? 'this conversation'}</h3>
        {s.conversation === conversation && (
          <button className="fx-ctl" title={`Keep ${name} as a section beside the conversation's primary`}
            onClick={() => { keepFeedSection(section, name); nav.closeAll() }}>Keep as section</button>
        )}
        <button className="fx-ctl fx-x fw-close" aria-label="Back to the conversation" onClick={() => nav.closeAll()}>✕</button>
      </header>
      <nav className="fx-about-tabs" aria-label="about">
        {SECTIONS.map(([k, label]) => (
          <button key={k} className={'fx-tab' + (k === section ? ' on' : '')} aria-pressed={k === section} onClick={() => open(k)}>{label}</button>
        ))}
      </nav>
      <div className="fx-sheet-body">
        {facts.error && <p className="fx-faint">Could not read this conversation's facts: {facts.error}</p>}
        {def?.body && (
          <def.body z={ABOUT_ZONE} options={sectionOptions(def, {})} setOption={noKeep} setSlot={noSlot}
            onOpenPost={goTo} chrome={asIs} conversation={conversation} />
        )}
      </div>
    </aside>
  )
}
