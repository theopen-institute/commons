/**
 * Types for the desk's fuzzy matcher, aliased in from `apps/frappe`.
 *
 * The module is plain JavaScript inside frappe's own bundle tree (see
 * `vite.config.js` for why it is borrowed rather than copied), so its surface is
 * declared here the same way the Bikram Sambat module's is — and for the same
 * reason: `allowJs` over a directory outside this project's root is a heavier
 * thing to turn on than writing down the one function that is used.
 *
 * The tuple is the whole of the contract. A miss is `[false, 0, []]` rather than
 * an exception, and the indices are positions in `str`, which is what lets a
 * caller mark the matched letters without matching a second time.
 */
declare module '@fuzzy-match' {
  /**
   * Find `pattern` in `str` as a subsequence, scored.
   *
   * @returns `[matched, score, matchedIndices]` — whether every character of
   * the pattern was found in order, how well it scored, and where each one
   * landed in `str`.
   */
  export function fuzzy_match(
    pattern: string,
    str: string,
  ): [matched: boolean, score: number, matches: number[]]
}
