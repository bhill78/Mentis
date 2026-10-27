import { useEffect, useRef, useState } from 'react'
import { score } from '../../composer/trigger'
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
    title: 'Reusable Form',
    note: 'Interactive forms · feedback, poll, survey, custom',
    icon: '📋',
    keywords: ['poll', 'survey', 'feedback', 'input', 'questionnaire'],
  },
]

export interface SlashPaletteProps {
  query: string
  onSelect: (commandId: string) => void
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

export default function SlashPalette({ query, onSelect, onDismiss, bind }: SlashPaletteProps) {
  const [at, setAt] = useState(0)
  const listRef = useRef<HTMLDivElement>(null)

  const filtered = SLASH_COMMANDS.filter((cmd) => matches(cmd, query))

  useEffect(() => {
    setAt(0)
  }, [query])

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
          onSelect(filtered[at].id)
          return true
        }
      }
      if (e.key === 'Escape') {
        onDismiss()
        return true
      }
      return false
    })
  }, [bind, filtered, at, onSelect, onDismiss])

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
          {filtered.map((cmd, i) => (
            <button
              key={cmd.id}
              type="button"
              className={'fc-slash-item' + (i === at ? ' on' : '')}
              data-cmd={cmd.id}
              role="option"
              aria-selected={i === at}
              onMouseEnter={() => setAt(i)}
              onMouseDown={(e) => e.preventDefault()}
              onClick={() => onSelect(cmd.id)}
            >
              <span className="fc-slash-icon" aria-hidden="true">{cmd.icon}</span>
              <div className="fc-slash-content">
                <div className="fc-slash-title-row">
                  <span className="fc-slash-cmd">{cmd.name}</span>
                  <span className="fc-slash-label">{cmd.title}</span>
                </div>
                <span className="fc-slash-desc">{cmd.note}</span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
