import { useEffect, useRef, useState } from 'react'
import { parseSpan, MIN_SPAN, MAX_SPAN } from '../../experimental/spec/timer'
import type { Post } from '../store'
import type { Id } from '../store'
import './timerDialog.css'

export type TimerMode = 'pomodoro' | 'stopwatch' | 'timebox'

export interface TimerDialogProps {
  query: string
  conversation: Id | null
  convName: string
  replyTo: Id | null
  parent?: Post
  existingText: string
  onInsert: (block: string) => void
  onClose: () => void
  bind: (handler: (e: React.KeyboardEvent) => boolean) => void
}

function defaultTitle(mode: TimerMode): string {
  switch (mode) {
    case 'pomodoro': return 'Pomodoro'
    case 'stopwatch': return 'Stopwatch'
    case 'timebox': return 'Timebox'
  }
}

function normalizeSpan(s: string): string {
  const t = s.trim()
  if (/^\d+$/.test(t)) return `${t}m`
  return t
}

export function slugifyName(title: string, mode: TimerMode, existingText: string): string {
  let base = (title.trim() || mode)
    .toLowerCase()
    .replace(/[^a-z0-9-]/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 30)
  if (!base || !/^[a-z]/.test(base)) {
    base = mode.toLowerCase()
  }
  let candidate = base
  let counter = 1
  while (
    existingText.includes(`name=${candidate}`) ||
    existingText.includes(`name="${candidate}"`)
  ) {
    counter++
    candidate = `${base}-${counter}`
  }
  return candidate
}

export function formatTimerMarkdown({
  mode,
  name,
  title,
  box,
  brk,
  aboutIds,
}: {
  mode: TimerMode
  name: string
  title: string
  box?: string
  brk?: string
  aboutIds: string[]
}): string {
  const parts = ['timer', 'version=1', `name=${name}`]
  const cleanTitle = title.trim().replace(/"/g, '')
  if (cleanTitle) {
    parts.push(`title="${cleanTitle}"`)
  }
  if (mode === 'pomodoro') {
    const cleanBox = normalizeSpan(box || '25m')
    const cleanBreak = normalizeSpan(brk || '5m')
    parts.push(`box=${cleanBox}`)
    parts.push(`break=${cleanBreak}`)
  } else if (mode === 'timebox') {
    const cleanBox = normalizeSpan(box || '30m')
    parts.push(`box=${cleanBox}`)
  }
  if (aboutIds.length > 0) {
    parts.push(`about="${aboutIds.join(', ')}"`)
  }
  return `\`\`\`${parts.join(' ')}\n\`\`\``
}

export default function TimerDialog({
  query,
  conversation,
  convName,
  replyTo,
  parent,
  existingText,
  onInsert,
  onClose,
  bind,
}: TimerDialogProps) {
  const q = query.trim().toLowerCase()
  const initialMode: TimerMode =
    q.startsWith('stopwatch') ? 'stopwatch' :
    q.startsWith('timebox') ? 'timebox' : 'pomodoro'

  const [mode, setMode] = useState<TimerMode>(initialMode)
  const [title, setTitle] = useState(defaultTitle(initialMode))
  const [titleEdited, setTitleEdited] = useState(false)
  const [box, setBox] = useState(initialMode === 'timebox' ? '30m' : '25m')
  const [brk, setBrk] = useState('5m')
  const [err, setErr] = useState<string | null>(null)
  const titleInputRef = useRef<HTMLInputElement>(null)

  // Context determination
  const postRef = parent?.number != null ? `Post #${parent.number}` : (replyTo ? `Post #${replyTo.slice(4, 10)}` : null)
  const convRef = parent?.home_name ?? convName ?? 'this conversation'
  const contextDisplay = replyTo
    ? `Replying to ${postRef} in ${convRef}`
    : `Conversation: ${convRef}`
  const parentHome = parent?.home || conversation
  const aboutIds: string[] = replyTo
    ? ([replyTo, parentHome].filter(Boolean) as string[])
    : (conversation ? [conversation] : [])

  const switchMode = (m: TimerMode) => {
    setMode(m)
    setErr(null)
    if (!titleEdited) {
      setTitle(defaultTitle(m))
    }
    if (m === 'pomodoro') {
      if (!box || box === '30m') setBox('25m')
      if (!brk) setBrk('5m')
    } else if (m === 'timebox') {
      if (!box || box === '25m') setBox('30m')
    }
  }

  const handleInsert = () => {
    // Validate durations
    if (mode === 'pomodoro') {
      const bNorm = normalizeSpan(box || '25m')
      const rNorm = normalizeSpan(brk || '5m')
      const bSec = parseSpan(bNorm)
      const rSec = parseSpan(rNorm)
      if (bSec === null || bSec < MIN_SPAN || bSec > MAX_SPAN) {
        setErr(`Work interval "${box}" is invalid (must be between 1m and 12h, e.g. 25m).`)
        return
      }
      if (rSec === null || rSec < MIN_SPAN || rSec > MAX_SPAN) {
        setErr(`Break interval "${brk}" is invalid (must be between 1m and 12h, e.g. 5m).`)
        return
      }
    } else if (mode === 'timebox') {
      const bNorm = normalizeSpan(box || '30m')
      const bSec = parseSpan(bNorm)
      if (bSec === null || bSec < MIN_SPAN || bSec > MAX_SPAN) {
        setErr(`Duration "${box}" is invalid (must be between 1m and 12h, e.g. 30m, 1h).`)
        return
      }
    }

    const name = slugifyName(title, mode, existingText)
    const block = formatTimerMarkdown({
      mode,
      name,
      title,
      box,
      brk,
      aboutIds,
    })
    onInsert(block)
  }

  useEffect(() => {
    bind((e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose()
        return true
      }
      if (e.key === 'Enter' && !e.shiftKey && !e.altKey && !e.ctrlKey && !e.metaKey) {
        handleInsert()
        return true
      }
      return false
    })
  }, [bind, mode, title, box, brk, aboutIds, existingText, titleEdited])

  useEffect(() => {
    titleInputRef.current?.focus()
  }, [])

  const matches =
    !q ||
    'timer'.startsWith(q) ||
    'pomodoro'.startsWith(q) ||
    'stopwatch'.startsWith(q) ||
    'timebox'.startsWith(q)

  if (!matches) {
    return (
      <div className="fc-timer-dialog">
        <p className="fw-meta" style={{ padding: '8px' }}>
          No slash command /{query}
        </p>
      </div>
    )
  }

  return (
    <div className="fc-timer-dialog" role="dialog" aria-label="Timer settings" data-mode={mode}>
      <div className="fc-timer-head">
        <div className="fc-timer-title-row">
          <span className="fc-timer-icon" aria-hidden="true">⏱</span>
          <span className="fc-timer-heading">/timer</span>
        </div>
        <div className="fc-timer-modes" role="tablist" aria-label="Timer mode">
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'pomodoro'}
            className={'fc-timer-mode-btn' + (mode === 'pomodoro' ? ' on' : '')}
            data-mode="pomodoro"
            onClick={() => switchMode('pomodoro')}
          >
            Pomodoro
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'stopwatch'}
            className={'fc-timer-mode-btn' + (mode === 'stopwatch' ? ' on' : '')}
            data-mode="stopwatch"
            onClick={() => switchMode('stopwatch')}
          >
            Stopwatch
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={mode === 'timebox'}
            className={'fc-timer-mode-btn' + (mode === 'timebox' ? ' on' : '')}
            data-mode="timebox"
            onClick={() => switchMode('timebox')}
          >
            Timebox
          </button>
        </div>
      </div>

      <div className="fc-timer-context">
        <span className="fc-timer-context-badge">Linked to</span>
        <span className="fc-timer-context-text" title={contextDisplay}>
          {contextDisplay}
        </span>
      </div>

      <form className="fc-timer-form" onSubmit={(e) => { e.preventDefault(); handleInsert(); }}>
        <div className="fc-timer-field">
          <label htmlFor="timer-title-input">Title</label>
          <input
            id="timer-title-input"
            ref={titleInputRef}
            type="text"
            className="fc-timer-input"
            value={title}
            onChange={(e) => { setTitle(e.target.value); setTitleEdited(true); }}
            placeholder={defaultTitle(mode)}
            aria-label="Timer title"
          />
        </div>

        {mode === 'pomodoro' && (
          <>
            <div className="fc-timer-field">
              <label htmlFor="timer-box-input">Work Interval</label>
              <div className="fc-timer-input-group">
                <input
                  id="timer-box-input"
                  type="text"
                  className="fc-timer-input"
                  value={box}
                  onChange={(e) => { setBox(e.target.value); setErr(null); }}
                  placeholder="25m"
                  aria-label="Work interval"
                />
                <div className="fc-timer-presets">
                  <button type="button" className={'fc-timer-preset-btn' + (box === '25m' ? ' on' : '')} onClick={() => setBox('25m')}>25m</button>
                  <button type="button" className={'fc-timer-preset-btn' + (box === '50m' ? ' on' : '')} onClick={() => setBox('50m')}>50m</button>
                </div>
              </div>
            </div>
            <div className="fc-timer-field">
              <label htmlFor="timer-break-input">Break Interval</label>
              <div className="fc-timer-input-group">
                <input
                  id="timer-break-input"
                  type="text"
                  className="fc-timer-input"
                  value={brk}
                  onChange={(e) => { setBrk(e.target.value); setErr(null); }}
                  placeholder="5m"
                  aria-label="Break interval"
                />
                <div className="fc-timer-presets">
                  <button type="button" className={'fc-timer-preset-btn' + (brk === '5m' ? ' on' : '')} onClick={() => setBrk('5m')}>5m</button>
                  <button type="button" className={'fc-timer-preset-btn' + (brk === '10m' ? ' on' : '')} onClick={() => setBrk('10m')}>10m</button>
                </div>
              </div>
            </div>
          </>
        )}

        {mode === 'timebox' && (
          <div className="fc-timer-field">
            <label htmlFor="timer-timebox-input">Duration</label>
            <div className="fc-timer-input-group">
              <input
                id="timer-timebox-input"
                type="text"
                className="fc-timer-input"
                value={box}
                onChange={(e) => { setBox(e.target.value); setErr(null); }}
                placeholder="30m"
                aria-label="Timebox duration"
              />
              <div className="fc-timer-presets">
                <button type="button" className={'fc-timer-preset-btn' + (box === '15m' ? ' on' : '')} onClick={() => setBox('15m')}>15m</button>
                <button type="button" className={'fc-timer-preset-btn' + (box === '30m' ? ' on' : '')} onClick={() => setBox('30m')}>30m</button>
                <button type="button" className={'fc-timer-preset-btn' + (box === '45m' ? ' on' : '')} onClick={() => setBox('45m')}>45m</button>
                <button type="button" className={'fc-timer-preset-btn' + (box === '1h' ? ' on' : '')} onClick={() => setBox('1h')}>1h</button>
              </div>
            </div>
          </div>
        )}

        {mode === 'stopwatch' && (
          <p className="fc-timer-note">
            Counts up from 0:00. No duration limit or breaks.
          </p>
        )}

        {err && <p className="fc-timer-error" role="alert">{err}</p>}

        <div className="fc-timer-actions">
          <button type="button" className="fc-timer-cancel" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="fc-timer-submit">
            Insert Timer
          </button>
        </div>
      </form>
    </div>
  )
}
