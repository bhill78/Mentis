/* WHERE WORKSPACES ARE REACHED: their rows in the switcher (WorkspaceRows), and the
 * sheet a Magnet or a Conversation asks from (WorkspaceChooser): a new workspace
 * starting from it, or one already there it is added to. A Magnet added to several
 * is several lists naming it. */

import { useEffect, useState, useSyncExternalStore } from 'react'
import { closeSheet, openSheet, Opt, Sec, Sheet } from '../frame/Sheet'
import * as nav from '../nav'
import { addToWorkspace, newWorkspaceFrom, refusalWords, workspaceDoors, type Curating } from './doors'
import { newWorkspace, loadWorkspaces, useWorkspaces } from './state'
import type { WorkspaceId } from './client'

const UNNAMED = 'Untitled workspace'

/** The switcher's rows: what there is, an unreadable one saying why, and a blank one. */
export function WorkspaceRows({ current, onChosen }: { current: WorkspaceId | null; onChosen: () => void }) {
  const list = useWorkspaces()
  const [naming, setNaming] = useState<string | null>(null)
  const [why, setWhy] = useState<string | null>(null)
  useEffect(() => { void loadWorkspaces() }, [])
  const open = (id: WorkspaceId) => { onChosen(); workspaceDoors().openWorkspace(id) }
  const make = async () => {
    setWhy(null)
    try {
      const got = await newWorkspace(naming?.trim() ? { name: naming.trim() } : {})
      setNaming(null)
      open(got.id)
    } catch (e) { setWhy(refusalWords(e)) }
  }
  return (
    <>
      <div className="fx-sec">Workspaces</div>
      <ul className="fx-rows wo-switch" aria-label="workspaces">
        {(list.rows ?? []).map((w) => w.unreadable !== undefined ? (
          <li key={w.id}><button className="fx-row" disabled data-workspace-row={w.id} data-refusal="unreadable" title={w.unreadable}>
            <span>{w.id}</span><small className="fw-meta">can’t be read: {w.unreadable}</small>
          </button></li>
        ) : (
          <li key={w.id}><button className={'fx-row' + (w.id === current ? ' on' : '')} data-workspace-row={w.id} onClick={() => open(w.id)}>
            <span className="fw-cname">{w.name || UNNAMED}</span><small className="fw-meta">{w.objects} {w.objects === 1 ? 'object' : 'objects'}</small>
          </button></li>
        ))}
        <li>
          {naming === null ? (
            <button className="fx-row" data-workspace-new onClick={() => setNaming('')}><span>New blank workspace</span><small className="fw-meta">belongs to no Conversation</small></button>
          ) : (
            <form className="wo-new" onSubmit={(e) => { e.preventDefault(); void make() }}>
              <input autoFocus aria-label="new workspace name" placeholder="Its name (optional)" value={naming} onChange={(e) => setNaming(e.target.value)}
                onKeyDown={(e) => { e.stopPropagation(); if (e.key === 'Escape') setNaming(null) }} />
              <button className="fx-ctl" type="submit">Make it</button>
            </form>
          )}
        </li>
        {(why ?? list.refusal?.message) && <li className="wo-refusal" role="alert">{why ?? list.refusal?.message}</li>}
      </ul>
    </>
  )
}

/* -- put this in a workspace ---------------------------------------------------- */

export const WORKSPACE_CHOOSER = 'workspace-chooser'
let choosing: Curating | null = null
const fns = new Set<() => void>()
const sub = (fn: () => void) => { fns.add(fn); return () => { fns.delete(fn) } }

/** Open the chooser for a Magnet or a Conversation, under the bar's title. */
export function chooseWorkspaceFor(what: Curating) {
  choosing = what
  fns.forEach((fn) => fn())
  /* the bar's title, by its id: the Magnet's actions reach this, and need none of the bar */
  const el = document.getElementById('title')
  if (el) openSheet(WORKSPACE_CHOOSER, el)
}

export function WorkspaceChooser() {
  const what = useSyncExternalStore(sub, () => choosing)
  const list = useWorkspaces()
  useEffect(() => { if (what) void loadWorkspaces() }, [what])
  if (!what) return null
  const go = (act: () => Promise<void>) => () => {
    closeSheet()
    act().catch((e) => nav.toast({ text: `Not done: ${refusalWords(e)}` }))
  }
  return (
    <Sheet id={WORKSPACE_CHOOSER} label={`put ${what.name} in a workspace`} className="wo-chooser">
      <Sec>Put {what.name} in a workspace</Sec>
      <Opt onPick={go(() => newWorkspaceFrom(what))} says="Starts with this and nothing else">New workspace from it</Opt>
      {(list.rows ?? []).filter((w) => w.unreadable === undefined).map((w) => (
        <Opt key={w.id} onPick={go(() => addToWorkspace(w.id, what))} says={`${w.objects ?? 0} objects`}>{w.name || UNNAMED}</Opt>
      ))}
      {list.refusal && <p className="wo-refusal" role="alert">{list.refusal.message}</p>}
    </Sheet>
  )
}
