/* Fluid sections, Design A: what was Placed, plus one optional feed, held in
   Node against the UI source (no server, no browser, no build).

     * a slot's `feed` is well formed only as the contract says: a section
       word, flat scalar options, never with follow or a pin; old slots are
       unchanged;
     * the effective feed: a registry word, `post`, `reading`, or none;
     * choosing a feed never touches what was placed;
     * what was placed is never narrowed -- not by Show, not by a feed --
       and is drawn first, the feed less what is placed after it;
     * captions and empty lines say what the section actually holds;
     * the menu's Brings in, as data.
   Run by tests/fluid_section_lanes_unit.mjs. */
import assert from 'node:assert/strict'
import { captionOf, captionText, feedChoices, nothingFrom, placedOf, sectionLanes, type FeedSource } from '../src/fluid/workspace/hooks'
import { feedOf, valid, withFeed, type Slot } from '../src/fluid/workspace/tree'
import { lookWords } from '../src/fluid/present/Pickers'

let checks = 0
const eq = (a: unknown, b: unknown, what: string) => { assert.deepEqual(a, b, what); checks++ }

const base: Slot = { follow: true, show: 'objects', items: [], present: 'cards' }
const slot = (s: Partial<Slot> & Record<string, unknown>) => ({ ...base, ...s }) as Slot
const zoneWith = (s: Record<string, unknown>) => ({ type: 'zone', id: 'z1', show: 'objects', slot: { ...base, ...s } })

/* -- Slot.feed: well formed ------------------------------------------------- */

eq(valid(zoneWith({})), true, 'an old slot, no feed, is unchanged')
eq(valid(zoneWith({ follow: false })), true, 'an old keeping slot is unchanged')
eq(valid(zoneWith({ follow: false, feed: { source: 'actions' } })), true, 'a registry feed on a slot that does not follow')
eq(valid(zoneWith({ follow: false, feed: { source: 'work', options: { tab: 'needs-you', collapsed: false, n: 3, period: null } } })), true,
  'flat scalar options, as a Home zone keeps them')
eq(valid(zoneWith({ follow: false, feed: null })), true, 'feed null is no feed, as pin null is no pin')
eq(valid(zoneWith({ follow: true, feed: { source: 'actions' } })), false, 'a feed never on a slot that follows what is read')
eq(valid(zoneWith({ follow: false, pin: 'ent-0123456789ab', feed: { source: 'actions' } })), false, 'nor with a pin')
eq(valid(zoneWith({ follow: false, feed: { source: 'Actions' } })), false, 'a source is a lower-case section word')
eq(valid(zoneWith({ follow: false, feed: { source: '9lives' } })), false, 'starting with a letter')
eq(valid(zoneWith({ follow: false, feed: { source: 'x'.repeat(41) } })), false, 'at most 40 long, as the server takes a show')
eq(valid(zoneWith({ follow: false, feed: {} })), false, 'a feed names its source')
eq(valid(zoneWith({ follow: false, feed: 'actions' })), false, 'a feed is a mapping')
eq(valid(zoneWith({ follow: false, feed: { source: 'work', options: { tab: { deep: 1 } } } })), false, 'options are flat')
eq(valid(zoneWith({ follow: false, feed: { source: 'work', options: ['tab'] } })), false, 'options are a mapping')
eq(valid(zoneWith({ follow: false, feed: { source: 'work', options: { 'bad key': 1 } } })), false, 'option keys as the server takes them')
eq(valid(zoneWith({ follow: false, feed: { source: 'work', options: Object.fromEntries(Array.from({ length: 21 }, (_, i) => [`k${i}`, i])) } })), false,
  'at most 20 options')
eq(valid(zoneWith({ follow: false, items: ['brain:ent-0123456789ab', 'needs-you:ask-1', 'live:p1:k'] })), true, 'every kind of placed item')

/* -- the effective feed --------------------------------------------------- */

eq(feedOf(slot({})), 'reading', 'follows what is read')
eq(feedOf(slot({ pin: 'ent-1' })), 'post', 'stays on one post')
eq(feedOf(slot({ pin: null })), 'reading', 'pin null is no pin')
eq(feedOf(slot({ follow: false })), null, 'only what is placed')
eq(feedOf(slot({ follow: false, feed: { source: 'media' } })), 'media', 'a registry feed')
eq(feedOf(undefined), null, 'no slot, no feed')

/* -- choosing a feed never touches what was placed -------------------------- */

const placed = ['live:p1:a', 'needs-you:ask-1', 'brain:ent-9']
const held = slot({ items: placed, pin: 'ent-1', show: 'forms', present: 'list' })
const toMedia = withFeed(held, 'media')
eq([toMedia.items, toMedia.follow, toMedia.pin, toMedia.feed], [placed, false, undefined, { source: 'media' }], 'to a registry feed: no follow, no pin')
eq([toMedia.show, toMedia.present], ['forms', 'list'], 'its Show and layout are kept for when it reads again')
eq(valid(zoneWith(toMedia as unknown as Record<string, unknown>)), true, 'and the slot is well formed')
const withOpts = { ...toMedia, feed: { source: 'media', options: { a: 1 } } }
eq(withFeed(withOpts, 'media').feed, { source: 'media', options: { a: 1 } }, 'the same source again keeps its options')
eq(withFeed(withOpts, 'actions').feed, { source: 'actions' }, 'another source starts from its own')
const toReading = withFeed(toMedia, 'reading')
eq([toReading.items, toReading.follow, 'feed' in toReading, 'pin' in toReading], [placed, true, false, false], 'back to following what is read')
eq(withFeed(toReading, 'post', 'ent-2').pin, 'ent-2', 'stay on a post')
eq(withFeed(toReading, 'post'), toReading, 'stay on nothing changes nothing')
const toNothing = withFeed(held, null)
eq([toNothing.items, toNothing.follow, 'pin' in toNothing, 'feed' in toNothing], [placed, false, false, false], 'nothing: only what is placed')

/* -- Placed is never filtered, and comes first ------------------------------- */

eq(placedOf(placed), { live: ['live:p1:a'], asks: ['needs-you:ask-1'], brain: ['brain:ent-9'] }, 'every placed item, by what draws it')
const listed = ['live:p2:x', 'live:p1:a', 'live:p2:y']
eq(sectionLanes(slot({ items: placed, show: 'forms' }), listed),
  { placed: placedOf(placed), feed: ['live:p2:x', 'live:p2:y'] },
  'Forms narrows the feed, not what was placed; what is placed is not brought in twice')
eq(sectionLanes(slot({ items: placed, follow: false, feed: { source: 'media' } }), listed),
  { placed: placedOf(placed), feed: [] }, 'with a registry feed: all of Placed, and the feed draws its own body')
eq(sectionLanes(slot({ items: placed, show: 'needs-you' }), listed).placed, placedOf(placed), 'What needs you: Placed is still all there')
eq(sectionLanes(slot({ items: placed, show: 'needs-you' }), listed).feed, [], 'and its feed draws its own cards')
eq(sectionLanes(slot({ items: placed, follow: false }), listed).feed, [], 'no feed: only what is placed')
/* Placed first, in every grouping (by reply too): the lanes are drawn in this order. */
eq(Object.keys(sectionLanes(slot({ items: placed }), listed)), ['placed', 'feed'], 'Placed, then the feed')

/* -- what the caption says --------------------------------------------------- */

const cap = (s: Partial<Slot> & Record<string, unknown>, number: number | null = 12, source?: FeedSource) =>
  captionText('Notes', captionOf({ slot: slot(s), number, root: number != null, source }))
eq(cap({ show: 'media', items: ['live:p1:a', 'live:p1:b'] }), 'Notes · Following #12 · Media · Placed · 2', 'following, narrowed, with things placed')
eq(cap({}), 'Notes · Following #12', 'Its objects is not said: it is the default')
eq(cap({}, null), 'Notes · Follows the post you read', 'nothing read yet')
eq(cap({ pin: 'ent-1', show: 'kinds', kinds: ['table', 'chart'] }), 'Notes · Stays on #12 · Tables, Charts', 'held on a post, some kinds by name')
eq(cap({ follow: false, feed: { source: 'actions' } }, null, { show: 'actions', name: 'Actions', scope: 'conversation' }),
  'Notes · Actions · this conversation', "a conversation's feed says whose")
eq(captionOf({ slot: slot({ follow: false, feed: { source: 'contents', options: { scope: 'post' } } }), number: 5, root: true,
  source: { show: 'contents', name: 'Contents', scope: 'conversation' }, name: 'Contents' }).words,
['#5 and its replies'], 'post-scoped Contents captions the selected subtree')
eq(captionOf({ slot: slot({ follow: false, feed: { source: 'contents', options: { scope: 'post' } } }), number: null, root: false,
  source: { show: 'contents', name: 'Contents', scope: 'conversation' }, name: 'Contents' }).words,
["post you're reading"], 'post-scoped Contents says what it follows before a post is read')
eq(cap({ follow: false, feed: { source: 'work' } }, null, { show: 'work', name: 'Work' }), 'Notes · Work', "Home's collection by its name")
/* A section named after its feed (Keep as section names it so) says the name once. */
eq(captionText('Actions', captionOf({ slot: slot({ follow: false, feed: { source: 'actions' } }), number: null, root: false,
  source: { show: 'actions', name: 'Actions', scope: 'conversation' }, name: 'Actions' })), 'Actions · this conversation', 'the feed is not named twice')
eq(captionText('Work', captionOf({ slot: slot({ follow: false, feed: { source: 'work' } }), number: null, root: false,
  source: { show: 'work', name: 'Work' }, name: 'Work' })), 'Work', 'nor a collection named as the section is')
eq(cap({ follow: false, feed: { source: 'gone' } }, null), 'Notes · gone', 'an unregistered source by its word')
eq(cap({ follow: false, items: ['a', 'b'] }, null), 'Notes · Placed · 2', 'only placed things')
eq(cap({ follow: false }, null), 'Notes · Holds what you place here', 'empty, it says what it is for')

/* -- what an empty feed says ------------------------------------------------- */

eq(nothingFrom(12, 'forms'), 'Nothing from #12 matches Forms.', 'nothing matched')
eq(nothingFrom(12, 'kinds', ['table']), 'Nothing from #12 matches Tables.', 'some kinds by name')
eq(nothingFrom(null, 'media'), 'Nothing from This post matches Media.', 'no number yet')
eq(nothingFrom(3, 'objects'), "#3 is text: it's in the conversation.", 'a post that is only words, as before')

/* -- the menu: Brings in ------------------------------------------------------- */

const sources: FeedSource[] = [
  { show: 'work', name: 'Work', scope: 'home' }, { show: 'guidance', name: 'Guidance', scope: 'conversation' },
  { show: 'brief', name: 'Brief', scope: 'conversation' }, { show: 'actions', name: 'Actions', scope: 'conversation' },
  { show: 'media', name: 'Media', scope: 'conversation' }, { show: 'followups', name: 'Follow ups', scope: 'conversation' },
  { show: 'needs-you', name: 'Needs you' },
]
const menu = (s: Partial<Slot> & Record<string, unknown>, reading = { number: 12 as number | null, reply: false } as { number: number | null; reply: boolean } | null) =>
  feedChoices(slot(s), reading, sources)
const rows = menu({})
eq(rows.filter((c) => c.group === 'main').map((c) => c.label), ['Nothing', "Follow what I'm reading", 'Stay on #12'], 'its own rows')
eq(rows.filter((c) => c.group === 'conversation').map((c) => c.to), ['actions', 'media', 'brief', 'followups', 'guidance'],
  'This conversation: the five, in the order offered')
eq(rows.filter((c) => c.group === 'more').map((c) => c.to), ['work', 'needs-you'], "More: Home's collections")
eq(rows.filter((c) => c.on).map((c) => c.to), ['reading'], 'following: one choice is on')
eq(menu({ pin: 'ent-1' }).filter((c) => c.on).map((c) => c.to), ['post'], 'held on a post')
eq(menu({ follow: false }).filter((c) => c.on).map((c) => c.to), [null], 'only what is placed')
eq(menu({ follow: false, feed: { source: 'media' } }).filter((c) => c.on).map((c) => [c.to, c.group]), [['media', 'conversation']], 'a registry feed')
eq(!!menu({}, null).find((c) => c.to === 'post')?.off, true, 'Stay on needs a post read first')
eq(menu({}, null).find((c) => c.to === 'post')?.label, 'Stay on this post', 'and says so without a number')
eq(menu({}, { number: 6, reply: true }).find((c) => c.to === 'post')?.says, '#6, whatever you read next', 'a reply: only itself')

/* -- Look's one row ----------------------------------------------------------- */

eq(lookWords({}), 'Clear', 'the default look')
eq(lookWords({ panel: 'solid', content: 'solid', opacity: 1 }), 'Solid', 'a preset by name')
eq(lookWords({ panel: 'tinted', content: 'solid', opacity: 0.4 }), 'Tinted panel, solid content', 'its own look in words')

console.log(`fluid section lanes: ${checks} checks passed`)
