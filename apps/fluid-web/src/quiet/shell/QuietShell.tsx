import type { ReactNode } from 'react'
import './quiet-shell.css'

/** Independent Quiet Chat surfaces supplied by the navigation, conversation and composer tracks. */
export interface QuietShellProps {
  /** Conversation-specific navigation, rendered in the supporting rail. */
  nav: ReactNode
  /** The conversation reading surface, rendered in the main scroll area. */
  content: ReactNode
  /** The composer, rendered below the conversation reading surface. */
  composer: ReactNode
}

export default function QuietShell({ nav, content, composer }: QuietShellProps) {
  return (
    <div className="quiet-shell">
      <header className="quiet-shell__header">
        <a href="/" className="quiet-shell__brand">Mentis</a>
        <span className="quiet-shell__workspace">Quiet Chat</span>
      </header>
      <div className="quiet-shell__body">
        <aside className="quiet-shell__rail" aria-label="Conversation navigation">{nav}</aside>
        <main className="quiet-shell__main">
          <div className="quiet-shell__content">{content}</div>
          <div className="quiet-shell__composer">{composer}</div>
        </main>
      </div>
    </div>
  )
}
