/** The Settings overlay: a focused place of its own, reached by the header gear.
 *
 *  Focused means focused (§5-H5-1). The frame hides the search line and the
 *  composer and disables Collect now while this is open, so nothing of the
 *  Summary shows beneath it; this view is the whole of the card's body.
 *
 *  It is also the home of the controls the approved frame has no other place
 *  for: the three "Navigate to …" actions, the Collection configuration panel,
 *  the earlier retained batches, "Reset position", and removal from the
 *  workspace -- which is kept apart from everything else, below, and says what
 *  it does.
 *
 *  Three things that are easy to confuse, and are deliberately not the same:
 *  the card's header `×` closes the **card**; **Cancel**, in the configuration
 *  panel, discards the staged configuration edits and nothing else; **Escape**
 *  (and the Return link here) leaves the overlay and **keeps** them. */
import { useEffect, useMemo, useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import type { MagnetResource } from './contract'
import BatchHistory from './BatchHistory'
import { leaveSettings, place, writePlace } from './places'
import { panelAt, panelDrafts, subscribePanelDrafts, takeSettingsReturn } from './panelDrafts'
import './configuration.css'

export interface SettingsViewProps {
  resource: MagnetResource
  collectionConfiguration?: ReactNode
  canReset: boolean
  onReset(): void
  onRemove(): void
  onSource(): void
  onConversation(): void
  onOrigin(): void
  hasOwnConversation: boolean
}

export default function SettingsView({ resource, collectionConfiguration, canReset, onReset, onRemove, onSource, onConversation, onOrigin, hasOwnConversation }: SettingsViewProps) {
  const s = useSyncExternalStore(resource.subscribe, resource.snapshot, resource.snapshot)
  const at = useMemo(() => panelAt(resource), [resource])
  const drafts = useSyncExternalStore((fn) => subscribePanelDrafts(at, fn), () => panelDrafts(at), () => panelDrafts(at))
  const here = place(s)
  // A committed save returns by `settingsReturn`. The panel that saved says so
  // through the draft store, because it is given its Magnet and not the frame.
  useEffect(() => { if (takeSettingsReturn(at)) leaveSettings(resource) }, [at, resource, drafts.returned])
  return <section className="q2-magnet-settings" aria-label="Magnet settings">
    <div className="q2-magnet-section-title">
      <h3 id="settings-title" tabIndex={-1}>Settings</h3>
      <button type="button" className="q2-magnet-link" onClick={() => leaveSettings(resource)}>← Return to {s.settingsReturn?.overlay === 'search' ? 'search' : s.settingsReturn?.tab ?? s.tab}</button>
    </div>
    <p className="q2-magnet-muted">Returning here, like Escape, keeps any unsaved configuration edits. Cancel, in the configuration panel, discards them.</p>

    <section>
      <h4>This Magnet</h4>
      <p>{s.title}</p>
      <div className="q2-magnet-conversations">
        <button type="button" className="q2-magnet-link" onClick={onSource}>Navigate to source Conversation →</button>
        <button type="button" className="q2-magnet-link" disabled={!hasOwnConversation} onClick={onConversation}>Navigate to full Magnet Conversation →</button>
        <button type="button" className="q2-magnet-link" onClick={onOrigin}>Navigate back to opening workspace →</button>
      </div>
      <p className="q2-magnet-muted">Schedules and change tracking are unavailable.</p>
    </section>

    {collectionConfiguration && <section><h4>Collection configuration</h4>{collectionConfiguration}</section>}

    <section>
      <details open={here.history} onToggle={(e) => writePlace(resource, 'settings', { history: e.currentTarget.open })}>
        <summary>Earlier retained batches</summary>
        {here.history && <BatchHistory resource={resource} />}
      </details>
    </section>

    <section className="q2-magnet-move">
      <h4>Position</h4>
      <p>Drag the puck or focus it and use arrow keys. Shift moves farther.</p>
      <div>
        <button type="button" disabled={!canReset} onClick={onReset}>Reset position</button>
      </div>
    </section>

    <section className="q2-magnet-danger" aria-label="Remove from workspace">
      <h4>Remove from the workspace</h4>
      <p>This takes the Magnet off this canvas. It is not the card's close button, which only shuts the card. The Magnet, its saved configuration, its retained batches and its Conversation are kept in the Brain and can be opened again from Magnet Management.</p>
      <button type="button" onClick={onRemove}>Remove this Magnet from the workspace</button>
    </section>
  </section>
}
