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
/* PRODUCTION'S BUILD DOES NOT MOVE (F6 final fix round, item 6). /fluid and
   production share one chunk. Rollup orders that chunk's modules as this
   page first reaches them, and names its exports in the order this page
   first asks for them. So the shared modules are reached here in the order
   the pre-F6 shell reached them, and the composer and Home -- the first of
   this page's own modules to ask the shared chunk for anything, then as now
   -- are reached before the rest. Production's shared chunk, and so its
   built JS, is then byte for byte what it was. See vite.config.ts too. */
import '../api'
import '../prose'
import '../experimental/renderable'
import '../experimental/objects'
import '../composer/draft'
import '../composer/Use'
import './Composer'
import './Home'
import Shell from './Shell'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Shell />
  </StrictMode>,
)
