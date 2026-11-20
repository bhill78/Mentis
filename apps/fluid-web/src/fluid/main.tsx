/* THE PAGE ENTRY. Once the Fluid workspace entry (stage F0); now it mounts
 * whichever interface the address names (../entry.ts): Quiet Chat at / and
 * /quiet2, Fluid at /fluid.
 *
 * Its own page and its own root: production's App is not mounted here, and
 * nothing here is mounted in it. It shares the theme, the atmospheres'
 * pictures and the Markdown renderers' styles; its frame (F6, the #184 demo)
 * is frame.css and conversation.css. Track B's workspace brings its own
 * workspace/workspace.css. */
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '../theme.css'
import '../app.css'
import '../atmosphere.css'
import '../experimental/renderable.css'

import { entryFor } from '../entry'

// QUIET CHAT IS THE INTERFACE; Fluid is legacy, at /fluid (owner, 2026-11-20).
// Which address opens which is one function: ../entry.ts.
async function mount() {
  const entry = entryFor(location)
  // A Fluid link saved at the root keeps where it pointed: replaced, so Back does not return here.
  if ('to' in entry) { location.replace(entry.to); return }
  const Root = entry.mount === 'quiet2'
    ? (await import('../quiet2/Quiet2')).default
    : entry.mount === 'quiet'
    ? (await import('../quiet/QuietChat')).default
    : (await import('../quiet/FluidEntry')).default
  createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>)
}
void mount()
