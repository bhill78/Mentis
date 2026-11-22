import type { RouteResult, RouteSource } from '../../fluid/surface/magnet/route'
import type { MagnetConfig } from '../../fluid/surface/magnet/types'

export interface SavedMagnet { id: `mag-${string}`; name: string; config?: MagnetConfig & { schema_version?: number }; reason?: string }
export type MagnetTab = 'Overview' | 'Posts' | 'Files' | 'Perspectives' | 'Conversation'
export interface MagnetSnapshot {
  title: string; loading: boolean; error?: string; summary?: RouteSource;
  results: RouteResult[]; next?: string; status?: string; reason?: string;
  x: number; y: number; tab: MagnetTab; pinned: boolean; expanded: boolean;
  previousOpen?: number; openedAt?: number;
}
export interface MagnetResource {
  id: string; brainKey: string; saved: SavedMagnet;
  snapshot(): MagnetSnapshot; subscribe(fn: () => void): () => void;
  update(change: Partial<MagnetSnapshot>): void;
  read(more?: boolean): Promise<void>; cancel(): void; dispose(): void;
}
export type MagnetGet = (path: string, signal?: AbortSignal) => Promise<{ status: number; body: unknown }>
