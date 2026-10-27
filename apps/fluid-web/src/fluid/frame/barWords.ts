/* WHAT THE BAR SAYS ABOUT STATUS, ONCE EACH (TopBar.tsx).
 *
 * The bar used to say the post read twice -- "● Reading #49 @brian" beside
 * the "This post · #49" tab -- and the author's face, ringed while they
 * worked, read as who was in the conversation; the count of other
 * conversations was a bare "●2" against this one's name. Now the This post
 * tab is the one place the post read is named (its author on hover), the
 * count says in words that it is elsewhere, and who is in this conversation
 * and who is working now are the column's: its strip of faces at the top
 * edge and the working line over the composer. */

/** The This post tab's hover: the post read and who wrote it. */
export function thisPostTitle(number: number | null, author: string | null | undefined): string {
  const by = author ? ` by ${author.startsWith('@') ? author : '@' + author}` : ''
  return number != null ? `Reading #${number}${by}` : 'This post: the post you read, in the workspace'
}

/** The title's mark for other conversations working or waiting on you. */
export function elsewhereWords(n: number): { short: string; word: string; title: string } {
  return {
    short: String(n),
    word: 'elsewhere',
    title: `${n} other ${n === 1 ? 'conversation is' : 'conversations are'} working or waiting on you`,
  }
}
