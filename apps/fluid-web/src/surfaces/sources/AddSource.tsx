import { useState } from 'react'
import type { Id } from '../../api'
import FilesystemFlow from './FilesystemFlow'
import SqliteFlow from './sqlite/SqliteFlow'
import type { Descriptor, Picker, SourcesRoute } from './route'

export function SourceKinds({ descriptors, connector, go, disabled = false }: {
  descriptors: Descriptor[]; connector?: string; go: (r: SourcesRoute) => void; disabled?: boolean
}) {
  return <><h2 className="src-h2">What kind of source</h2><div className="src-kinds" role="radiogroup" aria-label="What kind of source">
    {descriptors.filter(d => d.available).map(d => <button key={d.id} role="radio" aria-checked={connector === d.id}
      disabled={disabled} onClick={() => go({ at: 'flow', connector: d.id })}>
      <span aria-hidden="true">{d.binding === 'local-file' ? '▤' : '▱'}</span><span><b>{d.label}</b><small>{d.summary}</small></span>
    </button>)}</div><p className="src-faint">Not available yet: {descriptors.filter(d => !d.available).map(d => d.label).join(', ')}</p></>
}

export default function AddSource({ descriptors, connector, picker, me = null, go, onChanged = () => {} }: {
  descriptors: Descriptor[]; connector?: string; picker?: Picker; me?: Id | null
  go: (r: SourcesRoute) => void; onChanged?: () => void
}) {
  const [locked, setLocked] = useState(false)
  const [sqliteStep, setSqliteStep] = useState(1)
  const d = descriptors.find(d => d.id === connector)
  return <section className="src-page"><h1>Add a source</h1>
    {(!d || d.binding !== 'local-file' || sqliteStep === 1) && <SourceKinds descriptors={descriptors} connector={connector} go={r=>{setSqliteStep(1);setLocked(false);go(r)}} disabled={locked} />}
    {d?.available && d.binding === 'local-file' ? <SqliteFlow key={d.id} descriptor={d} picker={picker} me={me} go={go} onChanged={onChanged} onStep={setSqliteStep} /> : d?.available ? <FilesystemFlow key={d.id} descriptor={d} picker={picker} me={me} go={go} onChanged={onChanged} onLock={setLocked} />
      : <><Steps at={1} /><p>Choose what kind of source to add.</p></>}
  </section>
}

export function Steps({ at, reachable = at, onGo, editing = false }: {
  at: number; reachable?: number; onGo?: (n: number) => void; editing?: boolean
}) {
  return <ol className="src-steps" aria-label="steps">{['Source', 'Scope', 'Preview', 'Acquire'].map((n, i) =>
    editing && i === 0 ? null : <li key={n} className={i + 1 === at ? 'on' : i + 1 <= reachable ? 'done' : ''}>
      {onGo && i + 1 <= reachable && i + 1 !== at
        ? <button className="pill" onClick={() => onGo(i + 1)}>{i + 1} {n}</button>
        : <span aria-disabled={i + 1 > reachable || undefined}>{i + 1} {n}</span>}
    </li>)}</ol>
}
