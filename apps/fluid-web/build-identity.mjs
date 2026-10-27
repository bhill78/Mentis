// WHICH COMMIT THIS INTERFACE WAS BUILT FROM, written into the build itself.
//
// The server reads `dist/` from disk on every request, so what it serves is
// whatever was built last -- and nothing in a hashed asset name says which
// source that was. This stamps the answer into `dist/build-identity.json` at
// build time, where `/api/server` reads it. Observed from git when the build
// runs; `dirty` says the working tree differed from that commit, in which case
// the commit alone does not name what was built. Plain JS so it needs no Node
// type declarations the UI does not otherwise carry.
import { execFileSync } from 'node:child_process'

const git = (...args) => {
  try {
    return execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'] }).trim()
  } catch {
    return null
  }
}

export default function buildIdentity() {
  return {
    name: 'mentis-build-identity',
    apply: 'build',
    generateBundle() {
      const commit = git('rev-parse', 'HEAD')
      // untracked files count: a new file nobody committed is not that commit
      const status = git('status', '--porcelain')
      this.emitFile({
        type: 'asset',
        fileName: 'build-identity.json',
        source: JSON.stringify(
          {
            commit,
            commit_why_not: commit ? null : 'git could not be asked when this was built',
            dirty: status === null ? null : status.length > 0,
            untracked: status === null ? null : status.split('\n').filter((l) => l.startsWith('??')).length,
            // SOURCE_DATE_EPOCH (the package builder sets it to the commit
            // time) makes two builds of one commit byte-identical
            built_at: process.env.SOURCE_DATE_EPOCH ? Number(process.env.SOURCE_DATE_EPOCH) : Date.now() / 1000,
          },
          null,
          2,
        ),
      })
    },
  }
}
