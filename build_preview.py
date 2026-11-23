"""Reuse the approved preview shell and evidence; emit one offline HTML artifact."""
from pathlib import Path
import re

HERE = Path(__file__).parent
old = (HERE / 'baseline.html').read_text(encoding='utf-8')
script = old.split('<script>')[1].split('</script>')[0]
def function(name):
    return next(line for line in script.splitlines() if line.startswith('function '+name+'('))
data = '\n'.join(line for line in script.splitlines() if line.startswith(('const catalog=', 'const items=', 'const overview=')))
data = data.replace('File version · 148 bytes', 'File version · 133 bytes')
shared = ''
for name in ['inspection', 'questionDraft', 'setQuestionDraft', 'renameDraft', 'questionEditor', 'message', 'settings']:
    code = function(name)
    if name == 'inspection':
        code = code.replace('s.inspected', 'place().inspected')
        code = code.replace('<details class="provenance">', '<details class="provenance" id="provenance" '+"${place().provenance?'open':''}"+'>')
    if name == 'questionEditor':
        code = code.replace('Current TEST lacks rename; persistence requires a backend rename operation.', 'Rename is a browser-local proposal; backend support is not implemented here.')
        code = code.replace('Both naming actions are proposals requiring backend support; current TEST lacks rename.', 'Naming is a browser-local proposal.')
    if name == 'settings':
        code = code.replace('section id="settings-panel" class="settings-panel"', 'section id="settings-panel" class="settings-panel"')
        code = code.replace('${d.ids.length} of 20 selected.', '<span id="source-count">${d.ids.length}</span> of ${catalog.length} sample sources selected.')
        code = code.replace('<span>Web · unavailable</span>', '<span>Web pages</span><span>Web searches</span>')
        code = code.replace('<span>Database · unavailable</span><span>Repository · unavailable</span><span>Topic · unavailable</span><span>Connected service · unavailable</span>', '<span>Databases</span><span>Repositories</span><span>Topics</span><span>Connected services</span>')
        code = code.replace('Future source adapters · unavailable', 'Proposed future adapters')
        code = code.replace('These remain part of one universal source model. No adapter reads anything in this preview.', 'One source model: Conversations and their posts, files, Topics, web pages, web searches, databases, repositories and connected services. Conversation/post and text-file capture are supported in the existing candidate; future adapters above are not connected. All choices here are simulated.')
        code = code.replace('<div class="form-actions"><button class="primary" data-act="save-settings">', '<details><summary>Preview fixtures</summary><button class="link" id="empty-demo" data-act="empty-demo">Try an empty collection</button></details><div class="form-actions"><button class="primary" data-act="save-settings">')
    shared += '\n'+code

css = old.split('<style>')[1].split('</style>')[0]
workspace = '<div class="workspace"'+old.split('<div class="workspace"',1)[1].split('<div class="floating"',1)[0]
html = '''<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Magnet · Tabs and persistent composer</title><style>'''+css+(HERE/'hybrid.css').read_text(encoding='utf-8')+'''</style>
<header class="preview-bar"><div><strong>MAGNET</strong><span class="preview-note"> / Hybrid preview · design proposal</span></div><div class="row"><span class="preview-note">Standalone · sample content only</span><button id="notes-open" class="secondary">Preview notes</button><button id="reset">Reset demo</button></div></header>
'''+workspace+'''
<div class="floating" id="floating">
 <button id="puck" class="puck" aria-expanded="true" aria-controls="card">C<span class="mini" aria-hidden="true">▤</span></button>
 <div class="puck-name" id="puck-name" hidden>Calibration inquiry<br><span class="small">5 collected items</span></div>
 <section class="card" id="card" aria-label="Calibration inquiry Magnet">
 <header class="card-head"><div class="grow"><span class="card-title">Calibration inquiry</span><div class="head-sub" id="collection-count">5 collected items · evolving inquiry</div></div><button id="settings-toggle" class="icon" aria-label="Magnet settings" aria-expanded="false" aria-controls="settings-panel" title="Sources and collection settings"><svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m9 3-1 3-3 1-2 3 2 3v3l3 2 3-1 3 1 3-2v-3l2-3-2-3-3-1-1-3z"/><circle cx="11" cy="11" r="3"/></svg></button><button id="size" class="icon" aria-label="Expand Magnet" title="Expand Magnet">⤢</button><button id="close" class="icon" aria-label="Close Magnet" title="Close Magnet">×</button></header>
 <nav class="tabs" id="tabs" aria-label="Magnet views"></nav>
 <div class="toolbar" id="search-toolbar"><div class="searchline"><label class="sr-only" for="search">Search all Magnet information</label><input id="search" type="search" placeholder="Search this Magnet…" autocomplete="off"><button id="clear-search" class="clear-search icon" aria-label="Clear search" hidden>×</button></div></div>
 <div id="view" class="view" tabindex="-1"><div id="surface"></div></div>
 <form id="composer" class="persistent-composer"><div class="composer-shell"><div id="composer-context"></div><label class="sr-only" for="message">Message inside this Magnet</label><textarea id="message" rows="2" placeholder="Message this Magnet…"></textarea><div class="composer-actions"><div class="composer-tools"><button type="button" id="format" aria-label="Format text" title="Bold selected text">Aa</button><button type="button" id="address" aria-label="Address someone" title="Address someone">@</button><span class="key-hint">Enter ↑ · Shift Enter ↵</span></div><div class="split"><button class="primary" id="send" type="submit">Ask Mentis ↑</button><button class="primary" id="send-options" type="button" aria-label="Choose what sending does" aria-haspopup="menu" aria-expanded="false" aria-controls="send-menu">▾</button></div></div><div id="send-menu" class="send-menu" role="menu" aria-label="Ways to send" hidden><p class="dependency">What sending this does</p><button type="button" role="menuitemradio" data-send="ask">Ask Mentis<small>Illustrative reply in this preview</small></button><button type="button" role="menuitem" id="ask-someone">Ask someone…<small>Choose who to address</small></button><div id="people" hidden><button type="button" role="menuitemradio" data-person="@Caretaker">Ask @Caretaker</button><button type="button" role="menuitemradio" data-person="@Quill">Ask @Quill</button></div><button type="button" role="menuitemradio" data-send="record">Record only<small>Nobody is asked · Alt+Enter</small></button><p class="dependency">This choice is for this message only.</p></div></div><div class="composer-status">Illustrative conversation · no real agent run or evidence analysis</div></form>
 <footer class="card-foot"><span class="muted" id="collected-at"></span><button id="collect">Collect now · demo</button></footer>
 </section>
</div>
<div id="toast" class="toast" role="status" hidden></div><div id="announcer" class="sr-only" aria-live="polite" role="status"></div>
<dialog id="notes" class="notes-dialog" aria-labelledby="notes-title"><div class="row between"><h2 id="notes-title">About this preview</h2><button id="notes-close" class="icon" aria-label="Close preview notes">×</button></div><p>Standalone interaction proposal, using sample records. No backend, real agent, source access or TEST integration.</p><h3>Try the complete flow</h3><ol><li>Inspect calibration.txt in Summary. Type in the footer and send.</li><li>Conversation shows your message and an illustrative reply. Return to Summary resumes the inspection and reading position.</li><li>Search across the Magnet, filter by type, inspect a result and return to results.</li><li>Open the header gear for source and collection settings.</li><li>In Perspectives, create a question without a title; discuss it in the same footer.</li></ol><h3>Boundaries</h3><p>Factual Summary describes sample records. Evidence-grounded answers and synthesis are unavailable until agent access is verified as restricted to selected sources. Illustrative replies do not read the collection. An evidence context carries its reference only. Naming, renaming and question history are browser-local proposals. A Perspective may eventually become a full Conversation; that action is not implemented.</p><h3>State and keyboard</h3><p>Enter sends, Shift+Enter inserts a line, Ctrl/⌘+Enter sends, Alt+Enter records only. The split button chooses the action for one message. Escape dismisses the current layer and retains drafts. Creation, per-Perspective revision, rename and message drafts have separate slots. Cancel discards only the active editor draft. Tabs, search, inspection, history, scroll positions, draft and settings persist locally. Reset affects this demo only. The puck moves by dragging or arrow keys on desktop.</p><p>Settings demonstrates supported Conversation/post and text-file capture with proposed future adapters. Collection is simulated. Saving settings neither collects nor erases old copies. Text files are bounded to the first 64 KiB; links do not acquire targets. Preview fixtures includes an empty collection. Focused browser checks are not screen-reader certification.</p></dialog>
<script>\n'''+data+'\n'+shared+'\n'+(HERE/'hybrid.js').read_text(encoding='utf-8')+'\n</script></html>\n'
(HERE/'magnet-preview.html').write_text(html,encoding='utf-8')
(HERE/'preview-script.js').write_text(html.split('<script>')[1].split('</script>')[0],encoding='utf-8')
print('Built magnet-preview.html')
