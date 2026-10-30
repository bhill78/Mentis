/* ONE WORD AND ONE GLYPH PER ACTION (I-1, rev 3 §2.3; part P3).
 *
 * Every definition takes its label, glyph, group and synonyms from here, so
 * an id can never be drawn with two glyphs nor a glyph mean two ids. The old
 * words are synonyms, so the palette still finds them ("minimise" finds
 * Collapse and Put away; "restore" finds Bring back, Exit focus, Expand and
 * Restore layout).
 *
 *   ⇱ is Float only. ⧉ is retired. ◫ is Preview only (the bar's, not an
 *   action). ◆ is Keep. × is Close: this presentation on this browser device,
 *   never the shared surface. Remove from workspace is its own word and glyph. */

import type { ActionDef, ActionGroup, ActionId } from './types'

export interface Word {
  label: string
  glyph: string
  group: ActionGroup
  /** what it does, in a sentence (tooltips, the palette's second line) */
  says: string
  synonyms: readonly string[]
  shortcut?: string
}

export const WORDS: Record<Exclude<ActionId, `magnet.${string}` | 'conversation.makeMagnet'>, Word> = {
  open: { label: 'Open', glyph: '◨', group: 'resource', says: 'Open: the full view, with its own navigation', synonyms: ['read', 'open in home', 'go to', 'show'] },
  peek: { label: 'Peek', glyph: '◱', group: 'resource', says: 'Peek: look closer without changing anything (Esc returns)', synonyms: ['inspect', 'preview', 'look'] },
  openAsWorkspace: { label: 'Open as workspace', glyph: '⊡', group: 'resource', says: "Open as workspace: its own place, with its saved layout (Back returns)", synonyms: ['open as page', 'in the workspace'] },
  expand: { label: 'Expand', glyph: '⤢', group: 'view', says: 'Expand: one size larger, in place', synonyms: ['full screen', 'restore', 'unfold', 'enlarge', 'bigger', 'open wider'] },
  collapse: { label: 'Collapse', glyph: '⤡', group: 'view', says: 'Collapse: one size smaller, in place', synonyms: ['minimise', 'minimize', 'fold', 'shrink', 'smaller'] },
  resetSize: { label: 'Reset size', glyph: '⟲', group: 'view', says: 'Reset size: back to the size chosen for it automatically', synonyms: ['automatic size', 'default size'] },
  dock: { label: 'Dock', glyph: '⤓', group: 'arrange', says: 'Dock: back into the sections, beside where it was', synonyms: ['dock back', 'attach', 'unfloat'] },
  float: { label: 'Float', glyph: '⇱', group: 'arrange', says: 'Float: a window you can move and size', synonyms: ['window', 'pop out', 'detach', 'undock'] },
  makePrimary: { label: 'Make primary', glyph: '◎', group: 'arrange', says: 'Make primary: swap it into the primary place', synonyms: ['primary', 'swap'], shortcut: 'F' },
  back: { label: 'Back', glyph: '↶', group: 'arrange', says: 'Back: the primary before this one returns; they swap back', synonyms: ['swap back', 'previous primary'], shortcut: 'Esc' },
  focus: { label: 'Focus', glyph: '⛶', group: 'arrange', says: 'Focus: it takes the Focus area for now; everything else steps aside (Esc returns)', synonyms: ['lens', 'conversation focus', 'concentrate'], shortcut: 'Shift+F' },
  exitFocus: { label: 'Exit focus', glyph: '⤺', group: 'arrange', says: 'Exit focus: back to the arrangement before Focus', synonyms: ['restore', 'leave focus', 'unfocus'] },
  fullscreen: { label: 'Full screen', glyph: '▣', group: 'view', says: 'Full screen: this surface over everything, for now (Esc returns)', synonyms: ['full screen', 'maximise', 'maximize'] },
  exitFullscreen: { label: 'Exit full screen', glyph: '▢', group: 'view', says: 'Exit full screen: back where it was', synonyms: ['leave full screen'], shortcut: 'Esc' },
  putAway: { label: 'Put away', glyph: '⏏', group: 'arrange', says: 'Put away: into the launcher, keeping everything; Bring back returns it', synonyms: ['minimise', 'minimize', 'hide', 'stow'] },
  bringBack: { label: 'Bring back', glyph: '↥', group: 'arrange', says: 'Bring back: out of the launcher, to where it was put away from', synonyms: ['restore', 'unminimise', 'unminimize', 'show again'] },
  close: { label: 'Close', glyph: '×', group: 'arrange', says: 'Close here: this device stops showing it; the workspace keeps it (Reopen brings it back)', synonyms: ['hide here', 'dismiss'] },
  reopen: { label: 'Reopen', glyph: '↺', group: 'arrange', says: 'Reopen: show again on this device what was closed here', synonyms: ['open again', 'undo close'] },
  removeFromWorkspace: { label: 'Remove from workspace', glyph: '⌫', group: 'arrange', says: 'Remove from workspace: take it out of this workspace on every device (Undo brings it back)', synonyms: ['stop keeping', 'remove from here', 'unplace', 'close section', 'close window', 'delete', 'remove'] },
  search: { label: 'Search', glyph: '🔍', group: 'view', says: 'Search in what it holds', synonyms: ['find', 'find in'], shortcut: 'Ctrl+F' },
  filter: { label: 'Filter', glyph: '▽', group: 'view', says: 'Filter what it shows here; the resource is unchanged', synonyms: ['who', 'show agent work', 'hide agent work', 'hide others', 'reveal hidden', 'narrow', 'kinds'] },
  present: { label: 'Present', glyph: '▦', group: 'view', says: 'Present: how it lays out what it holds (cards, gallery, slides, list…)', synonyms: ['layout', 'mode', 'presentation', 'cards', 'gallery', 'slides'] },
  keep: { label: 'Keep', glyph: '◆', group: 'arrange', says: 'Keep: place it in a section, a window or on a Page', synonyms: ['pin as tab', 'keep as tab', 'save to', 'place', 'stay on'] },
  keepAsWindow: { label: 'Keep as window', glyph: '❐', group: 'arrange', says: 'Keep as window: what it shows now, in a window of its own', synonyms: ['open another', 'pop out', 'open in new window', 'new window'] },
  follow: { label: 'Follow', glyph: '⇢', group: 'arrange', says: 'Follow: show whatever its source selects, as it changes', synonyms: ['track', 'sync', 'live', 'follow what i read'] },
  hold: { label: 'Hold', glyph: '⇥', group: 'arrange', says: 'Hold: stop following and keep what it shows', synonyms: ['freeze', 'stay on this', 'stay on post', 'lock', 'pin content'] },
  newFollower: { label: 'New follower', glyph: '⇉', group: 'arrange', says: 'New follower: a section that follows what you read', synonyms: ['follow here', 'add follower'] },
  export: { label: 'Export', glyph: '⇩', group: 'share', says: 'Export what it holds, with its record', synonyms: ['download archive', 'export turn', 'export conversation', 'zip'] },
  details: { label: 'Details', glyph: 'ⓘ', group: 'details', says: 'Details: who, what, runs and provenance', synonyms: ['info', 'about', 'provenance'] },
  settings: { label: 'Look', glyph: '⚙', group: 'look', says: "Look: this surface's appearance", synonyms: ['settings', 'appearance', 'opacity', 'glass', 'solid', 'quiet', 'clear'] },
  copyLink: { label: 'Copy link', glyph: '🔗', group: 'share', says: 'Copy its link', synonyms: ['copy', 'link', 'share link', 'address'] },
  bringToFront: { label: 'Bring to front', glyph: '⇑', group: 'arrange', says: 'Bring to front: above the other windows', synonyms: ['raise', 'to front'] },
  tidy: { label: 'Tidy', glyph: '⊞', group: 'arrange', says: 'Tidy floating windows: line them up at the right', synonyms: ['arrange windows', 'line up', 'tidy floating windows'] },
  tidyAround: { label: 'Tidy around', glyph: '⌗', group: 'arrange', says: 'Tidy around Focus: line up what is beside it', synonyms: ['tidy around focus'] },
  fit: { label: 'Fit', glyph: '⇕', group: 'arrange', says: 'Fit to content: size it to what it holds', synonyms: ['fit to content', 'size to fit'] },
  split: { label: 'Split', glyph: '◧', group: 'arrange', says: 'Split: side by side, or top and bottom', synonyms: ['side', 'below', 'divide', 'split side by side', 'split top and bottom'] },
  merge: { label: 'Merge', glyph: '⧓', group: 'arrange', says: 'Merge with the section beside it', synonyms: ['join', 'combine'] },
  saveLayout: { label: 'Save layout', glyph: '⎙', group: 'arrange', says: "Save layout: this place's arrangement, for next time", synonyms: ['save', 'save this place', 'save arrangement'] },
  restoreLayout: { label: 'Restore layout', glyph: '⟳', group: 'arrange', says: 'Restore layout: back to the saved arrangement', synonyms: ['restore', 'revert', 'restore saved'] },
  undo: { label: 'Undo', glyph: '⎌', group: 'arrange', says: 'Undo the last change to the arrangement', synonyms: ['undo arrangement'], shortcut: 'Ctrl+Z' },
  resetPlace: { label: 'Reset this place', glyph: '⌂', group: 'arrange', says: "Reset this place: its default arrangement", synonyms: ['reset', 'default layout', 'start again'] },
  putAllAway: { label: 'Put all away', glyph: '⇊', group: 'arrange', says: 'Put all away: fold every floating window', synonyms: ['minimise all', 'minimize all', 'fold all'] },
  layouts: { label: 'Layouts', glyph: '▤', group: 'arrange', says: 'Layouts: apply, save, or set a default arrangement', synonyms: ['presets', 'named layouts', 'apply layout'] },
  sketch: { label: 'Sketch', glyph: '✎', group: 'arrange', says: 'Sketch a layout by drawing it', synonyms: ['draw layout', 'sketch a layout'] },
  makeRoom: { label: 'Make room', glyph: '↔', group: 'arrange', says: 'Make room: others move aside while you drag', synonyms: ['yield', 'push aside', 'displace'] },
  keepArrangement: { label: 'Keep arrangement', glyph: '✓', group: 'arrange', says: 'Keep arrangement: what is shown for now becomes the arrangement', synonyms: ['keep layout', 'keep this'] },
  moveUp: { label: 'Move up', glyph: '↑', group: 'arrange', says: 'Move up in the stack', synonyms: ['earlier', 'raise in stack'] },
  moveDown: { label: 'Move down', glyph: '↓', group: 'arrange', says: 'Move down in the stack', synonyms: ['later', 'lower in stack'] },
  showAsSheet: { label: 'Show as sheet', glyph: '▭', group: 'arrange', says: 'Show as a sheet over the column', synonyms: ['sheet', 'slide over'] },
  findAction: { label: 'Find an action…', glyph: '⌕', group: 'details', says: 'Find an action: every action here, by name or an old word', synonyms: ['palette', 'command', 'commands', 'actions'], shortcut: 'Ctrl+K' },
  'post.reply': { label: 'Reply', glyph: '↩', group: 'resource', says: 'Reply to this post in its thread', synonyms: ['answer', 'respond'] },
  'post.address': { label: 'Address', glyph: '@', group: 'resource', says: 'Address it to a participant', synonyms: ['mention', 'ask', 'assign'] },
  'post.annotate': { label: 'Annotate', glyph: '☺', group: 'resource', says: 'Annotate: react, comment or start a deep dive', synonyms: ['react', 'comment', 'deep dive', 'withdraw'] },
  'post.select': { label: 'Select', glyph: '☑', group: 'resource', says: 'Select it, to act on several posts together', synonyms: ['choose', 'multi select'] },
  'post.include': { label: 'Include here', glyph: '⊕', group: 'resource', says: 'Include this post in this conversation', synonyms: ['include in', 'add here'] },
  'post.removeInclusion': { label: 'Remove inclusion', glyph: '⊖', group: 'resource', says: 'Remove this included post from this conversation', synonyms: ['remove from here', 'exclude'] },
  'post.carries': { label: 'In this thread', glyph: '⋮', group: 'resource', says: 'What it carries: the objects in this thread', synonyms: ['carries', 'objects in this thread'] },
  'thread.replies': { label: 'Replies', glyph: '↳', group: 'resource', says: 'Its replies: the thread', synonyms: ['thread', 'replies', 'thread window', 'open thread'] },
  'selection.keepConversation': { label: 'Keep as conversation', glyph: '◈', group: 'resource', says: 'Keep as conversation: make a new conversation that includes the selected posts', synonyms: ['keep selected', 'group as conversation'] },
  'selection.include': { label: 'Include in…', glyph: '⊹', group: 'resource', says: 'Include in: show the selected posts in another conversation too', synonyms: ['include selected', 'add to conversation'] },
  'selection.remove': { label: 'Remove from here', glyph: '⊝', group: 'resource', says: 'Remove from here: end the selected posts\' inclusion in this conversation', synonyms: ['remove selected', 'end inclusion'] },
  'conversation.views': { label: 'Views', glyph: '☰', group: 'resource', says: 'Brief, Actions, Follow ups, Media and Guidance', synonyms: ['brief', 'actions', 'follow ups', 'media', 'guidance'] },
  'conversation.own': { label: 'Own', glyph: '★', group: 'resource', says: 'Open this conversation as its own place', synonyms: ['own place'] },
  'conversation.newHere': { label: 'New here', glyph: '✚', group: 'resource', says: 'Start a new conversation here', synonyms: ['new conversation'] },
  'conversation.topics': { label: 'Topics', glyph: '#', group: 'view', says: 'Topics: narrow the conversation to one', synonyms: ['topic', 'tags'] },
  'form.edit': { label: 'Edit form', glyph: '✍', group: 'resource', says: 'Edit the form', synonyms: ['fill', 'answer form'] },
  'form.validate': { label: 'Check form', glyph: '⚖', group: 'resource', says: 'Check what is missing or in conflict', synonyms: ['validate', 'check'] },
  'form.markReady': { label: 'Mark ready', glyph: '⚑', group: 'resource', says: 'Mark the answers ready (Done)', synonyms: ['done', 'ready', 'submit'] },
  'form.history': { label: 'History', glyph: '⌛', group: 'details', says: 'Its history and conflicts', synonyms: ['conflicts', 'versions'] },
  'file.download': { label: 'Download', glyph: '⤋', group: 'resource', says: 'Download the file', synonyms: ['save file'] },
  'link.openExternal': { label: 'Open link', glyph: '↗', group: 'resource', says: 'Open the link in a new tab', synonyms: ['open external', 'visit'] },
  'run.stop': { label: 'Stop', glyph: '■', group: 'resource', says: 'Stop the run: ends the session, not the work', synonyms: ['cancel', 'halt', 'end run'] },
  'run.consent': { label: 'Consent', glyph: '⚿', group: 'resource', says: 'What this run may do without asking', synonyms: ['permissions', 'allow', 'revoke'] },
}

type Worded = keyof typeof WORDS

/** A definition from its word: label, glyph, group and synonyms are the
 *  word's, never the provider's own. */
export function def(id: Worded, d: Pick<ActionDef, 'plane' | 'writes' | 'available' | 'run'> & Partial<Pick<ActionDef, 'lead' | 'multi'>>): ActionDef {
  const w = WORDS[id]
  return { id, label: w.label, glyph: w.glyph, group: w.group, synonyms: w.synonyms, ...(w.shortcut ? { shortcut: w.shortcut } : {}), ...d }
}

/** The sentence an action says (tooltip; the palette's second line). */
export const saysOf = (id: ActionId): string => (WORDS as Record<string, Word>)[id]?.says ?? id
