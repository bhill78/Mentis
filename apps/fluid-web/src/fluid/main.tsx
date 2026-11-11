/* THE FLUID WORKSPACE ENTRY (stage F0), served at /fluid from fluid.html.
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

// Quiet Chat has its own presentation layer; Fluid remains the default.
// Mark 2 is built beside Mark 1 at /quiet2 (docs/quiet-chat/MARK-2.md).
async function mount() {
  const Root = /^\/quiet2\/?$/.test(location.pathname)
    ? (await import('../quiet2/Quiet2')).default
    : /^\/quiet\/?$/.test(location.pathname)
    ? (await import('../quiet/QuietChat')).default
    : (await import('../quiet/FluidEntry')).default
  createRoot(document.getElementById('root')!).render(<StrictMode><Root /></StrictMode>)
}
void mount()
