/** The Settings overlay: a place of its own, reached by the header gear.
 *
 *  H1 lands it with the sections the frame extraction moved here, each still the
 *  working control it was inside the card body. H5 replaces the contents and
 *  owns the placement afterwards; the slot and the section order are the
 *  published seam.
 *
 *  Two different closes, two different labels: the header × closes the card,
 *  and removing the Magnet from the workspace lives here and says so. */
import { useSyncExternalStore } from 'react'
import type { ReactNode } from 'react'
import type { MagnetResource } from './contract'
import BatchHistory from './BatchHistory'
import { leaveSettings, place, writePlace } from './places'

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
  const here = place(s)
  return <section className="q2-magnet-settings" aria-label="Magnet settings">
    <div className="q2-magnet-section-title">
      <h3 id="settings-title" tabIndex={-1}>Settings</h3>
      <button type="button" className="q2-magnet-link" onClick={() => leaveSettings(resource)}>← Return to {s.settingsReturn?.overlay === 'search' ? 'search' : s.settingsReturn?.tab ?? s.tab}</button>
    </div>

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
        <button type="button" onClick={onRemove}>Remove this Magnet from the workspace</button>
      </div>
    </section>
  </section>
}
