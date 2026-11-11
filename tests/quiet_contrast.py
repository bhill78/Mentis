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
    # Not a bare `span`: a topic mark carries two -- `.qc-topic-bar`, first
    # in DOM order, decorative and `aria-hidden` -- and a bare selector
    # measured that one, silently, instead of the label a reader can read.
    ".qc-margin nav a:not([aria-current='page']) .qc-topic-label",
    ".qc-rail-tools button[aria-expanded='true']",
    ".qc-composer > label", ".qc-compose-actions > span",
    ".qc-compose-actions button",
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


# Rendered glyph backgrounds, including images and pseudo-elements.
TEXT_RANGES = r'''(selectors) => selectors.flatMap(selector => {
  const el = document.querySelector(selector); if (!el) return [];
  const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  const out = []; let n;
  while (n = walker.nextNode()) {
    if (!n.textContent.trim()) continue;
    const range = document.createRange(); range.selectNodeContents(n);
    const color = getComputedStyle(n.parentElement).color.match(/[\d.]+/g).map(Number);
    for (const r of range.getClientRects()) if (r.width && r.height && r.y >= 0 && r.bottom <= innerHeight)
      out.push({selector, text:n.textContent, color, x:r.x, y:r.y, width:r.width, height:r.height});
  } return out;
})'''

PIXELS = r'''async ({normal, hidden, ranges}) => {
  async function pixels(base64) {
    const img = new Image(); img.src='data:image/png;base64,'+base64; await img.decode();
    const canvas = document.createElement('canvas'); canvas.width=img.width; canvas.height=img.height;
    const ctx=canvas.getContext('2d'); ctx.drawImage(img,0,0);
    return {data:ctx.getImageData(0,0,img.width,img.height).data, width:img.width};
  }
  const fg=await pixels(normal), bg=await pixels(hidden);
  const lin = v => { v/=255; return v<=.04045 ? v/12.92 : ((v+.055)/1.055)**2.4; };
  const lum = c => .2126*lin(c[0])+.7152*lin(c[1])+.0722*lin(c[2]);
  const rows=[];
  for (const r of ranges) {
    let best=null;
    for(let y=Math.max(0,Math.ceil(r.y)); y<Math.floor(r.y+r.height); y++)
      for(let x=Math.max(0,Math.ceil(r.x)); x<Math.min(bg.width,Math.floor(r.x+r.width)); x++) {
        const j=(y*bg.width+x)*4;
        // Only pixels changed by hiding text: samples lie on painted glyphs,
        // rather than on a bright patch between words or beyond the text.
        const delta=Math.abs(fg.data[j]-bg.data[j])+Math.abs(fg.data[j+1]-bg.data[j+1])+Math.abs(fg.data[j+2]-bg.data[j+2]);
        if(delta<40) continue;
        const paper=[bg.data[j],bg.data[j+1],bg.data[j+2]];
        const a=r.color.length>3?r.color[3]:1;
        const ink=r.color.slice(0,3).map((v,i)=>v*a+paper[i]*(1-a));
        const l1=lum(ink), l2=lum(paper), ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
        if(!best || ratio<best.ratio) best={ratio,x,y,paper,ink};
      }
    if(best) rows.push({...r, ...best});
  } return rows;
}'''


def rendered_legible(page, selectors):
    """Measure pixels behind visible glyphs, with text temporarily hidden."""
    import base64
    ranges = page.evaluate(TEXT_RANGES, selectors)
    normal = page.screenshot()
    style = page.add_style_tag(content="*{color:transparent!important;-webkit-text-fill-color:transparent!important;text-shadow:none!important;caret-color:transparent!important}")
    try:
        hidden = page.screenshot()
    finally:
        style.evaluate("s => s.remove()")
    return page.evaluate(PIXELS, dict(normal=base64.b64encode(normal).decode(),
                                      hidden=base64.b64encode(hidden).decode(), ranges=ranges))
