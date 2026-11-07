/* TRACK D: the restrained icon strip beginning with Settings -- quick theme
 * (◐, cycling system/light/dark on the same store the Settings panel's own
 * select reads), in-content search (⌕) and an optional pinned toolbar. One
 * component, mounted once in Chrome's `.qc-aside` cell: pinning is a CSS
 * position change on this same strip (toolbar.css), not a second render of
 * it, so Settings' own open panel and the strip's tab order stay exactly
 * what they were, pinned or not. */
import { setTheme, useTheme, type Theme } from '../../fluid/frame/look'
import QuietSearch from '../search/QuietSearch'
import BackgroundControl from '../surface/BackgroundControl'
import { setSurfaceAppearance, useSurfaceAppearance } from '../surface/Surface'
import './toolbar.css'

const NEXT_THEME: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
const THEME_WORD: Record<Theme, string> = { system: 'System', light: 'Light', dark: 'Dark' }

export default function Toolbar() {
  const theme = useTheme()
  const look = useSurfaceAppearance()
  return <div className="qc-toolbar">
    <BackgroundControl />
    <button type="button" className="qc-tool-button" aria-label={`Theme: ${THEME_WORD[theme]}`}
      title={`Theme: ${THEME_WORD[theme]} (click to change)`}
      onClick={() => setTheme(NEXT_THEME[theme])}>◐</button>
    <QuietSearch />
    <button type="button" className="qc-tool-button" aria-label="Pin toolbar" aria-pressed={look.pinToolbar}
      title="Pin toolbar" onClick={() => setSurfaceAppearance({ pinToolbar: !look.pinToolbar })}>
      <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
        <path d="M12 2a6 6 0 0 0-6 6c0 4.5 6 12 6 12s6-7.5 6-12a6 6 0 0 0-6-6Z" />
        <circle cx="12" cy="8" r="2" />
      </svg>
    </button>
  </div>
}
