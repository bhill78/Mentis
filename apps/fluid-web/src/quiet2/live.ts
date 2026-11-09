/// <reference types="vite/client" />
/* A READ-ONLY PREVIEW (live-data round).
 *
 * Mark 2 is tested against the DAY-TO-DAY Brain read-only: the preview's
 * proxy (vite.config.ts, MENTIS_READONLY=1) refuses every request that is not
 * a read, and tells the page so here. The page then offers nothing that
 * writes: no composer, no reply, no edit, no choosing or making a look, no
 * editing instructions. Reading, viewing and arranging stay. */
export const READ_ONLY = import.meta.env.VITE_MENTIS_READONLY === '1'

export const READ_ONLY_WHY = 'Read-only preview: posting, replying and editing are off here.'
