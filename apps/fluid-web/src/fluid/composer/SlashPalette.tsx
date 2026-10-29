import { useEffect, useRef, useState } from 'react'
import { score } from '../../composer/trigger'
import { matchWorkflows, type WorkflowRow } from './workflows'
import './slashPalette.css'

export interface SlashCommand {
  id: string
  name: string
  title: string
  note: string
  icon: string
  keywords?: string[]
}

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    id: 'timer',
    name: '/timer',
    title: 'Timer',
    note: 'Pomodoro, Stopwatch, or Timebox helper',
    icon: '⏱',
    keywords: ['pomodoro', 'stopwatch', 'timebox', 'clock'],
  },
  {
    id: 'form',
    name: '/form',
    title: 'Forms',
    note: 'Interactive forms · feedback, poll, survey, custom',
    icon: '📋',
    keywords: ['poll', 'survey', 'feedback', 'input', 'questionnaire'],
  },
]

/** One row of the palette: a command, or an established Workflow after them. */
export type SlashItem = { kind: 'command'; cmd: SlashCommand } | { kind: 'workflow'; workflow: WorkflowRow }

/** The rows for what follows the `/`: the commands that match, then the
 *  Workflows whose names contain it. */
export function slashItems(query: string, workflows: WorkflowRow[] = []): SlashItem[] {
  return [
    ...SLASH_COMMANDS.filter((cmd) => matches(cmd, query)).map((cmd) => ({ kind: 'command' as const, cmd })),
    ...matchWorkflows(workflows, query).map((workflow) => ({ kind: 'workflow' as const, workflow })),
  ]
}

export interface SlashPaletteProps {
  query: string
  onSelect: (commandId: string) => void
  /** established Workflows offered after the commands */
  workflows?: WorkflowRow[]
  onWorkflow?: (w: WorkflowRow) => void
  onDismiss: () => void
  bind: (handler: (e: React.KeyboardEvent) => boolean) => void
}

function matches(cmd: SlashCommand, q: string): boolean {
  if (!q) return true
  const clean = q.startsWith('/') ? q.slice(1).trim().toLowerCase() : q.trim().toLowerCase()
  if (!clean) return true
  if (cmd.id.toLowerCase().startsWith(clean)) return true
  if (cmd.name.toLowerCase().startsWith('/' + clean)) return true
  if (cmd.title.toLowerCase().startsWith(clean)) return true
  if (cmd.keywords?.some((k) => k.toLowerCase().startsWith(clean))) return true
  if (score(cmd.name, clean) !== null) return true
  if (score(cmd.title, clean) !== null) return true
  return false
}

export default function SlashPalette({ query, onSelect, workflows, onWorkflow, onDismiss, bind }: SlashPaletteProps) {
  const [at, setAt] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  const filtered = slashItems(query, onWorkflow ? workflows : [])
  const pick = (it: SlashItem) => (it.kind === 'command' ? onSelect(it.cmd.id) : onWorkflow?.(it.workflow))

  /* Back to the first row when the query changes, or when the Workflows are
     read again and the list changes under the highlight. */
  useEffect(() => {
    setAt(0)
  }, [query, filtered.length])

  useEffect(() => {
    bind((e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        setAt((i) => (filtered.length ? (i + 1) % filtered.length : 0))
        return true
      }
      if (e.key === 'ArrowUp') {
        setAt((i) => (filtered.length ? (i - 1 + filtered.length) % filtered.length : 0))
        return true
      }
      if ((e.key === 'Enter' || e.key === 'Tab') && !e.shiftKey) {
        if (filtered[at]) {
          pick(filtered[at])
          return true
        }
      }
      if (e.key === 'Escape') {
        onDismiss()
        return true
      }
      return false
    })
  }, [bind, filtered, at, onSelect, onWorkflow, onDismiss])

  useEffect(() => {
    listRef.current?.querySelector('.fc-slash-item.on')?.scrollIntoView({ block: 'nearest' })
  }, [at])

  return (
    <div className="fc-slash-menu" ref={listRef} role="listbox" aria-label="slash commands">
      <p className="fc-slash-head">Slash commands: Enter picks · Esc dismisses</p>
      {filtered.length === 0 ? (
        <div className="fc-slash-empty">No command matching /{query}</div>
      ) : (
        <div className="fc-slash-list">
          {filtered.map((it, i) => (
            <button
              key={it.kind === 'command' ? it.cmd.id : 'workflow:' + it.workflow.entry}
              type="button"
              className={'fc-slash-item' + (i === at ? ' on' : '')}
              data-cmd={it.kind === 'command' ? it.cmd.id : undefined}
              data-workflow={it.kind === 'workflow' ? it.workflow.entry : undefined}
              role="option"
              aria-selected={i === at}
              onMouseEnter={() => setAt(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => pick(it)}
            >
              {it.kind === 'command' ? (
                <>
                  <span className="fc-slash-icon" aria-hidden="true">{it.cmd.icon}</span>
                  <div className="fc-slash-content">
                    <div className="fc-slash-title-row">
                      <span className="fc-slash-cmd">{it.cmd.name}</span>
                      <span className="fc-slash-label">{it.cmd.title}</span>
                    </div>
                    <span className="fc-slash-desc">{it.cmd.note}</span>
                  </div>
                </>
              ) : (
                <>
                  <span className="fc-slash-icon" aria-hidden="true">↻</span>
                  <div className="fc-slash-content">
                    <div className="fc-slash-title-row">
                      <span className="fc-slash-cmd">{it.workflow.name}</span>
                      <span className="fc-slash-label">Workflow</span>
                    </div>
                    <span className="fc-slash-desc">Use it for this request</span>
                  </div>
                </>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
