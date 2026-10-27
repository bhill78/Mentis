/* ------------------------------------------------------------------------ *
 * THE RUNTIME MARKS. What a Participant is drawn as when nobody has chosen a
 * picture for it: the mark of the runtime that carried it.
 *
 * WHICH RUNTIME IS NEVER A PROPERTY OF THE PARTICIPANT. A Participant has no
 * runtime; each execution has one. On a Turn the mark is the runtime that
 * wrote THAT Turn, read off its `written_by`. Anywhere else it is where the
 * Participant last ran, which the server reads from the record. A name that
 * has never run has no mark and keeps its initial.
 *
 * Drawn here, shipped with the interface, never uploaded: these are ours to
 * draw as vectors, and an uploaded SVG is served as text on purpose. Each is
 * a simple stand-in on the brand's colour, in one 32-unit box, so a vendor's
 * own artwork can replace any entry without touching anything else.
 * ------------------------------------------------------------------------ */

export const RUNTIME_LABEL: Record<string, string> = {
  claude: 'Claude',
  codex: 'Codex',
  antigravity: 'Antigravity',
  ollama: 'Ollama',
  lmstudio: 'LM Studio',
}

const MARKS: Record<string, { bg: string; draw: React.ReactNode }> = {
  claude: {
    bg: '#D97757',
    draw: (
      <g stroke="#fff" strokeWidth="2.6" strokeLinecap="round">
        {Array.from({ length: 8 }, (_, i) => {
          const a = (i * Math.PI) / 4
          return (
            <line
              key={i}
              x1={16 + Math.cos(a) * 2.5}
              y1={16 + Math.sin(a) * 2.5}
              x2={16 + Math.cos(a) * (i % 2 ? 7.5 : 9.5)}
              y2={16 + Math.sin(a) * (i % 2 ? 7.5 : 9.5)}
            />
          )
        })}
      </g>
    ),
  },
  codex: {
    bg: '#111111',
    draw: (
      <g stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" fill="none">
        <path d="M9 11l5 5-5 5" />
        <path d="M16 21h7" />
      </g>
    ),
  },
  antigravity: {
    bg: '#3B6FE0',
    draw: (
      <g fill="none" stroke="#fff" strokeWidth="2">
        <ellipse cx="16" cy="16" rx="10" ry="4.2" transform="rotate(-28 16 16)" />
        <circle cx="16" cy="16" r="3.4" fill="#fff" stroke="none" />
        <circle cx="24.4" cy="11.4" r="1.6" fill="#fff" stroke="none" />
      </g>
    ),
  },
  ollama: {
    bg: '#2B2B2B',
    draw: (
      <g fill="#fff">
        <rect x="10.5" y="6" width="3" height="7" rx="1.5" />
        <rect x="18.5" y="6" width="3" height="7" rx="1.5" />
        <rect x="9" y="11" width="14" height="14" rx="7" />
        <circle cx="13.5" cy="17" r="1.2" fill="#2B2B2B" />
        <circle cx="18.5" cy="17" r="1.2" fill="#2B2B2B" />
      </g>
    ),
  },
  lmstudio: {
    bg: '#6E56CF',
    draw: (
      <g fill="#fff">
        <rect x="8" y="9" width="12" height="3" rx="1.5" />
        <rect x="11" y="14.5" width="13" height="3" rx="1.5" />
        <rect x="8" y="20" width="10" height="3" rx="1.5" />
      </g>
    ),
  },
}

export const hasMark = (runtime: string | null | undefined): runtime is string =>
  !!runtime && runtime in MARKS

/** The runtime a Turn's `written_by` names, or null. `written_by` is what the
 *  server observed of the writer: `claude/1a2b3c4d`, or the observed form
 *  `observed:codex/<instance>/<participant>`. Anything else -- a person, an
 *  unattributed request -- names no runtime, and none is guessed. */
export function runtimeOf(writtenBy: string | null | undefined): string | null {
  if (!writtenBy) return null
  const head = writtenBy.replace(/^observed:/, '').split('/')[0]
  return hasMark(head) ? head : null
}

export function RuntimeMark({ runtime, size }: { runtime: string; size: number }) {
  const m = MARKS[runtime]
  if (!m) return null
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" aria-hidden="true">
      <circle cx="16" cy="16" r="16" fill={m.bg} />
      {m.draw}
    </svg>
  )
}
