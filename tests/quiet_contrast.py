"""THE CONTRAST QUIET CHAT'S INK ACTUALLY REACHES, for any suite that needs it.

Lifted out of ``test_quiet_chat_browser.py`` at P0 because more than one
package has to measure it: G paints new grounds under every one of these
selectors and must show that the faintest ink on each still clears AA, and the
reconciled-findings suite checks the same thing on the grounds Quiet has
today. One implementation, so two suites cannot disagree about what 4.5:1
means here.

Nothing in this module opens a browser or asserts; it is helpers only.
"""
from __future__ import annotations

#: The contrast an element's own ink actually reaches over the layers painted
#: behind it -- the computed colours, composited, not the tokens' nominal
#: values. WCAG 2.x relative luminance.
CONTRAST = r"""
(selector) => {
  const el = document.querySelector(selector)
  if (!el) return null
  const nums = (c) => (String(c).match(/[\d.]+/g) || [0, 0, 0]).map(Number)
  const lin = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }
  const lum = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2])
  const over = (top, under) => {
    const a = top.length > 3 ? top[3] : 1
    return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a))
  }
  const layers = []
  for (let n = el; n; n = n.parentElement) layers.push(nums(getComputedStyle(n).backgroundColor))
  let paper = [255, 255, 255]
  for (let i = layers.length - 1; i >= 0; i--) paper = over(layers[i], paper)
  const ink = over(nums(getComputedStyle(el).color), paper)
  const pair = [lum(ink), lum(paper)].sort((a, b) => b - a)
  return { ratio: (pair[0] + 0.05) / (pair[1] + 0.05), paper: lum(paper) }
}
"""

#: Every place Quiet Chat writes in a quieter ink than body text, plus the
#: body and the primary action. --qc-type-meta is 13px, so AA's 4.5:1 for
#: normal text is the bar everywhere here; none of this is large text.
#:
#: A CHOSEN ROW AND AN ORDINARY ONE ARE NAMED APART. `aria-current` tints the
#: row with the accent wash, which lifts the ground under the quietest ink in
#: the interface, so the two grounds are different measurements -- and a bare
#: `nav a span` would measure whichever row the server happened to list first.
QUIET_INK = (
    ".qc-eyebrow", ".qc-post > header time", ".qc-post > header a",
    ".qc-post > footer", ".qc-fluid", ".qc-brand span", ".qc-body",
    ".qc-margin", ".qc-margin h2",
    ".qc-margin nav a[aria-current='page'] span",
    ".qc-margin nav a:not([aria-current='page']) span",
    ".qc-heading nav button[aria-expanded='true']",
    ".qc-composer > label", ".qc-compose-actions > span",
    ".qc-compose-actions button",
)
#: The same, inside the conversation popover, which floats on --surface-raised
#: -- the lightest ground in dark, and so the hardest one here.
POPOVER_INK = (
    ".qc-navigation h2",
    ".qc-navigation a[aria-current='page'] span",
    ".qc-navigation a[aria-current='page'] strong",
    ".qc-navigation a:not([aria-current='page']) span",
    ".qc-navigation a:not([aria-current='page']) strong",
)


def reads_in(page, base, conversation, name):
    """Open a conversation with posts, the margin and the composer all drawn."""
    page.goto(base + f"/quiet#/c/{conversation}")
    page.get_by_role("heading", name=name, exact=True).wait_for()
    page.locator(".qc-post").first.wait_for()
    page.get_by_label("Continue the conversation").wait_for()


def legible(page, selectors):
    """Each selector's ratio, having checked it is actually on the page."""
    out = {}
    for selector in selectors:
        got = page.evaluate(CONTRAST, selector)
        assert got is not None, f"{selector} is not on the page to measure"
        out[selector] = got
    return out
