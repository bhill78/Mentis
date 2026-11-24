import type { RouteResult, RouteSource } from '../../fluid/surface/magnet/route'
import type { MagnetConfig } from '../../fluid/surface/magnet/types'

export interface SavedMagnet { id: `mag-${string}`; name: string; config?: MagnetConfig & { schema_version?: number }; reason?: string }

/** The approved hybrid order. Summary is first and the default; `All` is the
 *  real key the owner's design labels "All" (v1 called it `Overview`). */
export const MAGNET_TABS = ['Summary', 'All', 'Posts', 'Files', 'Perspectives', 'Conversation'] as const
export type MagnetTab = typeof MAGNET_TABS[number]
/** An overlay is a place of its own: it keeps its own reading position. */
export type MagnetOverlay = null | 'search' | 'settings'
export type MagnetPlaceKey = MagnetTab | 'search' | 'settings'
export const MAGNET_PLACE_KEYS = [...MAGNET_TABS, 'search', 'settings'] as const

/** Everything one view remembers about where the reader was in it. */
export interface MagnetPlace {
  scroll: number
  inspected: string | null
  inspectScroll: number
  inspectOrigin: string | null
  provenance: boolean
  history: boolean
}

export type MagnetSearchKind = 'Summary' | 'Posts' | 'Files' | 'Perspectives' | 'Conversation' | 'Settings' | 'Batches'
export type MagnetSearchType = 'All' | MagnetSearchKind
export const MAGNET_SEARCH_TYPES = ['All', 'Summary', 'Posts', 'Files', 'Perspectives', 'Conversation', 'Settings', 'Batches'] as const
/** The one result the reader opened from the results list. */
export interface MagnetSearchTarget { kind: MagnetSearchKind; item?: string; lens?: string; message?: string }

/** A deep snapshot of where the reader was, taken before navigating away.
 *  `searchTarget` and `placeSnapshot` are copies, never live references: that
 *  is what makes a return survive an intervening search. */
export interface MagnetRoute {
  tab: MagnetTab
  overlay: MagnetOverlay
  searchTarget: MagnetSearchTarget | null
  lens: string | null
  query: string
  searchType: MagnetSearchType
  searchListScroll: number
  placeKey: MagnetPlaceKey
  placeSnapshot: MagnetPlace
}

/** One searchable thing a view holds. `open()` navigates to it. */
export interface SearchEntry { key: string; kind: MagnetSearchKind; title: string; text: string; open(): void }
/** A view's contribution to the universal Magnet index. `entries()` is what is
 *  already in hand; `complete()` owes everything else that source holds, so the
 *  index is over collected information and not over what happened to be loaded.
 *  `bound()` is the honest sentence when `complete()` cannot finish. */
export interface SearchSource {
  entries(): SearchEntry[]
  complete?(query: string, signal?: AbortSignal): Promise<SearchEntry[]>
  queryDependent?: boolean
  bound?(): string | null
}

/** The composer's discussion reference. Only the reference and its label are
 *  persisted: captured collection text never enters device storage. */
export interface MagnetContext {
  ref: string
  kind: 'post' | 'file' | 'image' | 'attachment' | 'perspective' | 'batch'
  label: string
  text?: string
}

/** WHAT ONE SEND TOOK WITH IT, written when it goes out and read when it is
 *  recorded. The answer can land while the footer is not mounted -- the card
 *  closed, or settings open -- so what the sent message carried cannot be read
 *  off the card at that point: by then it is the next message's. Held under the
 *  send's own key, so the recorded post settles its own send exactly once. */
export interface MagnetCarried {
  op: string
  context: MagnetContext | null
  suppressed: boolean
  /** where it was written from, taken while that view was still on the screen */
  from: MagnetRoute
}

export interface MagnetSnapshot {
  // identity and liveness -- never persisted
  title: string; loading: boolean; error?: string; summary?: RouteSource
  results: RouteResult[]; next?: string; status?: string; reason?: string
  activation?: { post: string; artifact: { ref: string; digest?: string; size?: number; media_type?: string }; at: number; state: string } | null
  collecting?: boolean; collectionMessage?: string
  // persisted working state (localStorage; workingState.ts maps v1 onto exactly these)
  x: number; y: number; open: boolean; wide: boolean; tab: MagnetTab; overlay: MagnetOverlay
  places: Record<MagnetPlaceKey, MagnetPlace>
  query: string; searchType: MagnetSearchType; searchTarget: MagnetSearchTarget | null; searchListScroll: number
  lens: string | null
  returnRoute: MagnetRoute | null; settingsReturn: MagnetRoute | null
  context: MagnetContext | null; contextSuppressed: boolean
  carried: MagnetCarried | null
  agentId?: string
  assistanceMode?: 'ordinary' | 'retained'
  batchSelection?: { ref: string; digest: string }
  // open-transition baseline (in memory, per tab, as before)
  previousOpen?: number; openedAt?: number
}
export interface MagnetResource {
  id: string; brainKey: string; saved: SavedMagnet;
  snapshot(): MagnetSnapshot; subscribe(fn: () => void): () => void;
  update(change: Partial<MagnetSnapshot>): void;
  read(more?: boolean): Promise<void>; cancel(): void; dispose(): void;
  collect?(): Promise<void>;
  selectBatch?(batch: { ref: string; digest: string } | null): Promise<void>;
}
export type MagnetGet = (path: string, signal?: AbortSignal) => Promise<{ status: number; body: unknown }>
