// THE SERVER'S COPY OF THE UI'S MARKDOWN READERS, built from the UI source.
//
// `src/experimental/spec/check.ts` and everything it imports -- the block
// reader, the generic attribute rules and every type's body reader -- bundled
// into one plain script, `dist/render-check.js`, by the same `vite build` that
// builds the interface (the plugin below), so a release carries the readers
// its own UI runs and nobody copies a file by hand. The server runs it in an
// embedded engine (mentis/conversation/render_check.py) to tell an agent what
// will not render; nothing here is loaded by the browser.
//
// The script defines one global, `MentisRenderCheck`, whose `checkRendering`
// returns the report. It must import nothing that draws: a bundle that pulls
// in anything from node_modules (React) is refused rather than shipped.
//
//   node render-check.mjs <out.js>     the same bundle, written to a file
import { build } from 'esbuild'
import { readFileSync, realpathSync, statSync, writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, posix, relative, resolve, sep } from 'node:path'

const HERE = dirname(fileURLToPath(import.meta.url))
export const ENTRY = 'src/experimental/spec/check.ts'
export const FILE = 'render-check.js'

// The real path of `p`: every symlink and junction followed, and on Windows the
// case as it is on disk. Null when there is no such file.
const real = (p) => { try { return realpathSync.native(p) } catch { return null } }
const realFile = (p) => { const r = real(p); try { return r && statSync(r).isFile() ? r : null } catch { return null } }

// THE SOURCE IS RESOLVED AND READ HERE, NOT BY ESBUILD. esbuild's own resolver
// lists every ancestor of the working directory, and on Windows it treats an
// ancestor it may traverse but not list as fatal ("Cannot read directory ...:
// Access is denied") -- which is what a sandboxed build sees when the tree
// sits under a user profile only its owner may list. Only relative imports
// inside src/ are followed, which is also the rule the bundle is held to.
//
// CONTAINMENT IS JUDGED ON THE FILE THAT WOULD BE READ, never on the text of
// the import: a specifier is written with forward slashes (a `\` is a
// separator to Windows, so `..\..\x` climbs just as `../../x` does), and the
// file it names is taken to its real path -- links and junctions followed --
// which must lie under the real ui/src/, compared exactly, case included, so
// a drive letter, a UNC share, a case variant or a link out of src/ is refused
// however it was spelt. Only `./` and `../` specifiers are followed at all.
function uiSourceOnly() {
  const root = real(HERE)
  const src = real(resolve(HERE, 'src'))
  const refuse = (p) => ({ errors: [{ text: `render-check must import only UI source, not ${p}` }] })
  return {
    name: 'ui-source-only',
    setup(b) {
      b.onResolve({ filter: /.*/ }, (args) => {
        const entry = args.kind === 'entry-point'
        const spec = args.path.replaceAll('\\', '/')
        if (!root || !src || spec.includes(':') || spec.includes('\0')) return refuse(args.path)
        if (!entry && !spec.startsWith('./') && !spec.startsWith('../')) return refuse(args.path)
        const base = posix.normalize(posix.join(entry ? '' : posix.dirname(args.importer), spec))
        const hit = [base, base + '.ts', base + '/index.ts'].map((c) => realFile(resolve(root, c))).find(Boolean)
        if (!hit || !hit.startsWith(src + sep)) return refuse(args.path)
        const path = relative(root, hit).split(sep).join('/')
        if (!path.startsWith('src/')) return refuse(args.path)
        return { path, namespace: 'ui', pluginData: hit }
      })
      b.onLoad({ filter: /.*/, namespace: 'ui' }, (args) =>
        ({ contents: readFileSync(args.pluginData, 'utf8'), loader: 'ts' }))
    },
  }
}

// Exported so a test can build the same source with esbuild's own resolver and
// hold the two outputs to each other (tests/render_check_resolver_unit.mjs).
export const OPTIONS = {
  absWorkingDir: HERE,
  bundle: true,
  write: false,
  metafile: true,
  format: 'iife',
  globalName: 'MentisRenderCheck',
  platform: 'neutral',
  // The embedded engine (QuickJS) has ES2020 syntax; newer syntax is lowered.
  target: 'es2020',
  charset: 'utf8',
  legalComments: 'none',
  logLevel: 'silent',
}

/** The bundle of `entry` (ENTRY unless a test names another file under ui/). */
export async function renderCheckBundle(entry = ENTRY) {
  const out = await build({ ...OPTIONS, entryPoints: [entry], plugins: [uiSourceOnly()] })
  const outside = Object.keys(out.metafile.inputs).filter((f) => !f.startsWith('ui:src/'))
  if (outside.length) throw new Error(`render-check must import only UI source, not ${outside.join(', ')}`)
  return '/* Mentis render check: built from ui/' + entry + ' by ui/render-check.mjs. Do not edit. */\n' + out.outputFiles[0].text
}

/** Vite plugin: emit the bundle into the build's own output. */
export default function renderCheck() {
  return {
    name: 'mentis-render-check',
    apply: 'build',
    async generateBundle() {
      this.emitFile({ type: 'asset', fileName: FILE, source: await renderCheckBundle() })
    },
  }
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const to = process.argv[2]
  if (!to) throw new Error('usage: node render-check.mjs <out.js>')
  writeFileSync(to, await renderCheckBundle(), 'utf8')
}
