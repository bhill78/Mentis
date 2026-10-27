import { createContext } from 'react'

/* THE TURN A CITATION SITS IN, AS ITS QUOTE (Sources C, C1.6, C4).
 *
 * When an extracted citation cannot be reproduced here, its chip shows the
 * source and location the citation carries and the passage the Turn quoted
 * with it. A chip is drawn deep inside a run of text -- often a slice of a
 * paragraph, or a paragraph rendered by its caller's own reader -- so it
 * cannot see that passage itself. `Prose` provides, for the whole Turn,
 * how to find the quote of a citation in it (`turnQuote` in prose.tsx);
 * null outside any Turn. Kept in its own module so the chip and the reader
 * do not import each other. */
export const TurnQuote = createContext<((cite: string) => string | undefined) | null>(null)
