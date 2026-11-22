/* OPENING AN INPUT'S FORM AT THE EXACT BLOCK ITS REQUEST NAMES.
 *
 * An input waits on one response set: one named block, in one part of one
 * post. A post may carry several forms, so going to the post is not enough:
 * the block drawn for exactly that post and name is found by the key every
 * drawing of a block already carries (`data-block-key`) and brought into
 * view. Two spellings of that key are drawn today:
 *
 *   Turn <post>[ part N]/@<name>:<type>   Fluid and Classic (experimental/objects.ts)
 *   q2:<post>:<i>/@<name>:<type>          Quiet Chat's posts (quiet2/Post.tsx)
 *
 * Never the nearest block, and never one by its title. Where the same name
 * is drawn in more than one part of the post, only the part the set names is
 * taken; where that cannot be told, nothing is marked. */

export interface DrawnBlock { post: string; part: number; name: string }

/** What a drawn block's key says it is, or null for a key that names no block. */
export function blockOf(key: string | null | undefined): DrawnBlock | null {
  if (!key) return null
  const m = /^Turn (\S+?)(?: part (\d+))?\/@([^:/]+):[^/]*$/.exec(key) ?? /^q2:([^:/]+):(\d+)\/@([^:/]+):[^/]*$/.exec(key)
  return m ? { post: m[1], part: m[2] ? Number(m[2]) : 0, name: m[3] } : null
}

/** Which of these drawn keys is the block of exactly this post and name (and
 *  part, where more than one part draws that name): its index, or -1. */
export function pickBlock(keys: (string | null | undefined)[], post: string, part: number, name: string): number {
  const same = keys.map((k, i) => ({ b: blockOf(k), i })).filter((x) => x.b && x.b.post === post && x.b.name === name)
  const parts = new Set(same.map((x) => x.b!.part))
  if (parts.size === 1) return same[0].i
  const exact = same.filter((x) => x.b!.part === part)
  return exact.length && new Set(exact.map((x) => x.b!.part)).size === 1 ? exact[0].i : -1
}

let landing = 0

/** Wait (up to `ms`) for that exact block to be drawn, then scroll it into
 *  view and mark it `data-landed`. Resolves whether it was found. */
export function landAtBlock(post: string, part: number, block: string, ms = 10000, may: () => boolean = () => true): Promise<boolean> {
  const mine = ++landing
  const until = Date.now() + ms
  return new Promise((done) => {
    const look = () => {
      if (mine !== landing || !may()) return done(false)
      const drawn = [...document.querySelectorAll<HTMLElement>('[data-block-key]')].filter((x) => !x.closest('.q2-gdock'))
      const el = drawn[pickBlock(drawn.map((x) => x.dataset.blockKey), post, part, block)]
      if (el) {
        document.querySelectorAll('[data-landed]').forEach((x) => x.removeAttribute('data-landed'))
        el.setAttribute('data-landed', '')
        el.scrollIntoView({ block: 'center', behavior: 'auto' })
        return done(true)
      }
      if (Date.now() > until) return done(false)
      window.setTimeout(look, 120)
    }
    look()
  })
}
