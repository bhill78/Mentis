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
import './fluid.css'
import './frame/frame.css'
import './conversation/conversation.css'
import Shell from './Shell'
import QuietShell from '../quiet/shell/QuietShell'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    {location.pathname === '/quiet'
      ? <QuietShell nav={<div>nav</div>} content={<div>content</div>} composer={<div>composer</div>} />
      : <Shell />}
  </StrictMode>,
)
