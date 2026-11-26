/** The Settings overlay: a focused place of its own, reached by the header gear.
 *
 *  Focused means focused (§5-H5-1). The frame hides the search line and the
 *  composer and disables Collect now while this is open, so nothing of the
 *  Summary shows beneath it; this view is the whole of the card's body.
 *
 *  WHAT OPENS FIRST (owner request ent-3191baeb33d2 §4). "When I open Settings,
 *  I want to configure the Magnet." So the first thing in the body is the
 *  identity slot (the name and general settings), then the sources and
 *  collection controls, then position. There is no standing navigation, no
 *  identity recital, no heading repeated from the card, and no explanation of
 *  what Escape does -- that sentence appears only while there are unsaved
 *  configuration edits for it to be about. Collection history, opening something
 *  outside the Magnet and removal from the workspace are all disclosed: real
 *  controls, one click away, not occupying the first screen.
 *
 *  TWO SLOTS, FILLED BY THE PARTS THAT OWN THEM (this is the contract):
 *    `identity`                 Magnet name and applicable general settings.
 *    `collectionConfiguration`  sources, adding/removing/configuring them,
 *                               collection behaviour and its filters.
 *  Both are optional `ReactNode`s rendered in that order at the top of the body;
 *  this view adds no heading of its own above `identity`, so the slot's own
 *  first control is the first thing in Settings. With no `identity` slot the
 *  Magnet's name is shown as plain text, which is what this build did before.
 *
 *  Three things that are easy to confuse, and are deliberately not the same:
 *  the card's header `×` closes the **card**; **Cancel**, in the configuration
 *  panel, discards the staged configuration edits and nothing else; **Escape**
 *  (and the × here) leaves the overlay and **keeps** them. */
import { useEffect, useMemo, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import type { MagnetResource } from './contract'
import BatchHistory from './BatchHistory'
import { leaveSettings, place, writePlace } from './places'
import { panelAt, panelDrafts, subscribePanelDrafts, takeSettingsReturn } from './panelDrafts'
import './configuration.css'

export interface SettingsViewProps {
  resource: MagnetResource
  /** The name and general settings, first in the body. Part B's controls. */
  identity?: ReactNode
  collectionConfiguration?: ReactNode
  canReset: boolean
  onReset(): void
  onRemove(): void
  onSource(): void
  onConversation(): void
  onOrigin(): void
  hasOwnConversation: boolean
}

export default function SettingsView({ resource, identity, collectionConfiguration, canReset, onReset, onRemove, onSource, onConversation, onOrigin, hasOwnConversation }: SettingsViewProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const at = useMemo(() => panelAt(resource), [resource])
  const drafts = useSyncExternalStore((fn) => subscribePanelDrafts(at, fn), () => panelDrafts(at), () => panelDrafts(at))
  const here = place(s)
  // A committed save returns by `settingsReturn`. The panel that saved says so
  // through the draft store, because it is given its Magnet and not the frame.
  useEffect(() => { if (takeSettingsReturn(at)) leaveSettings(resource) }, [at, resource, drafts.returned])
  const back = s.settingsReturn?.overlay === 'search' ? 'search' : s.settingsReturn?.tab ?? s.tab
  return <section className="q2-magnet-settings" aria-label="Magnet settings">
    {/* The overlay's own title line, in the panel's framing (round-3 mockups):
        a titled surface inside the panel, not a form on its background. */}
    <div className="q2-magnet-overlay-head">
      <h3 id="settings-title" tabIndex={-1}>Settings</h3>
      <button type="button" className="q2-magnet-icon" aria-label={`Close settings and return to ${back}`} title={`Close settings and return to ${back}`}
        onClick={() => leaveSettings(resource)}>×</button>
    </div>
    {/* SETTINGS IS FOR CHANGING SOMETHING LATER (owner's correction
        `ent-8a4357b5f7fc`, amendment §4). It is not a step in getting started:
        a Magnet made from a sentence arrives already configured, already
        collected and already refreshing, and nothing in creation sends anybody
        here. So this says what the place is for, once, where someone who
        arrived expecting a setup form would otherwise be looking for it. */}
    <p className="q2-magnet-muted">Everything here is already set. Change it when you want this Magnet to follow something else, or to look more or less often.</p>
    {/* Only while there is something unsaved for it to be about. */}
    {drafts.settings && <p className="q2-magnet-muted">Closing this, like Escape, keeps these unsaved edits. Cancel discards them.</p>}

    {identity ?? <section className="q2-magnet-identity"><h4>Name</h4><p>{s.title}</p></section>}

    {collectionConfiguration && <section aria-label="Sources and collection">{collectionConfiguration}</section>}

    <section className="q2-magnet-move">
      <h4>Position</h4>
      <div>
        <button type="button" disabled={!canReset} onClick={onReset}>Reset position</button>
      <details><summary>Position controls</summary><span>Drag the puck or use the arrow keys. Hold Shift to move farther.</span></details>
      </div>
    </section>

    <section>
      <details open={here.history} onToggle={(e) => writePlace(resource, 'settings', { history: e.currentTarget.open })}>
        <summary>Collection history</summary>
        {here.history && <BatchHistory resource={resource} />}
      </details>
    </section>

    {/* The one place external navigation lives: asked for explicitly, never
        standing in a view (§3). */}
    <section>
      <details>
        <summary>Open outside this Magnet</summary>
        <div className="q2-magnet-conversations">
          <button type="button" className="q2-magnet-link" onClick={onSource}>Source Conversation →</button>
          <button type="button" className="q2-magnet-link" disabled={!hasOwnConversation} onClick={onConversation}>Full Conversation →</button>
          <button type="button" className="q2-magnet-link" onClick={onOrigin}>Where this was opened from →</button>
        </div>
      </details>
    </section>

    <section className="q2-magnet-danger" aria-label="Remove from workspace">
      <details>
        <summary>Remove from the workspace</summary>
        <p>Removes this Magnet from the canvas. Its settings and collection remain available in Magnet Management.</p>
        <button type="button" onClick={onRemove}>Remove this Magnet from the workspace</button>
      </details>
    </section>
  </section>
}
