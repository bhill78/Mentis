# Quiet Magnet additions — implementation plan

Request: ent-0c1b8e7e9fa0 / opr-480c3d1e3467. Owner feedback ent-d9805bb7f8bc;
approval ent-ea447212ce00; TEST follow-up ent-341640ddc1eb. Base b1146760.

Smallest coherent candidate includes all three additions, with the accepted yellow
appearance, on an isolated disposable fixture. No production change or main merge.

* A (complex; HTTP/React/state; independent review): new MiniConversation.tsx,
  conversation.ts/css and focused tests. Existing saved distinct Conversation C,
  actual history/replies, explicit owner sends through the existing posting door,
  actual Work read status and full-Conversation callback. No creation/repair of C,
  no change to main Conversation navigation or post store. Abort/stale/Brain guards,
  no blind resend after uncertain writes, retain independent draft while mounted.
* B (bounded; React/CSS; final rendered review): Magnet.tsx, magnet.css and new
  indicators helper/tests. Hover/focus actions to real Posts/Files/Perspectives and
  new-item information; exact scope labels (source tally versus loaded selected
  results), unknown counts unavailable. No continuous animation or fake totals.
* Parent (complex; HTTP/React/browser): Host.tsx, Quiet2.tsx, Markers.tsx, new
  Management module, fixture/proxy tools and integration tests. Rail entry below
  Brain group/separator. Find/select/open existing supported records and create via
  sanctioned arrangement Magnet creation; unsupported configuration stays visible.
  Mini mounted through additive prop after B merges. Expanded card is a nonmodal
  canvas card rather than an inert full-page stage, so main Conversation/composer
  remain operable. Existing full-Conversation/item navigation uses guarded paths;
  legacy history details can resume but must not silently discard mini draft.

A and B work on separate claimed clones/branches. Parent owns shared seams;
integrate with git merge. No backend/dispatch/execution changes are planned.

Independent plan review before implementation is required for send/create/identity
boundaries. Final independent review checks substantive code and boundary/security;
blocking findings are corrected and re-reviewed on what changed.

## Revision checked against Quill's verdict opr-dc014d9b2569

Both blocking plan findings are addressed here before implementation. The new
write-capable proxy will require a completed synthetic fixture manifest under this
checkout, verify the upstream corpus identity itself before listening/forwarding
mutations, and refuse writes whenever identity cannot be confirmed. Every write
is additionally checked against that identity at request time. A loopback port by
itself is never a fixture gate. Exact raw forwarded paths are allowlisted; encoded
aliases are refused; authority/cookies/method overrides are stripped, while the
page's X-Mentis-Brain binding is preserved and checked by the real server.

The fixture page keeps global readOnly:true. A dedicated capability read, supplied
only by the identity-verified fixture proxy, enables only mini Conversation sends
to the pre-existing C and Management creation into the explicit A arrangement.
The main Conversation remains readable alongside the card; its send/edit/agent
controls stay visibly unavailable in this bounded fixture. Normal Mentis (including
a properly integrated TEST release) uses existing !READ_ONLY and Brain-binding
checks. The new UI does not enable unrelated preview writes. This limit is shown
in the page and handoff, not disguised as a fully writable environment.

Agreed A interface: default MiniConversation({resource: MagnetResource, onFull():
void, canWrite: boolean}); A owns its new conversation.ts HTTP/state seam. It uses
CLIENT_HEADERS, confirmBrain/page binding and an explicit X-Mentis-Brain on writes,
refuses unknown/moved identity, reads GET /api/conversations/<C> and actual Work,
posts only through the existing owner post door, never fallback to a source C or
participants[0]. Existing C must differ from every source. Parent supplies the
scoped capability. Draft state stays with the resource across collapse/tab changes;
expose hasMiniDraft(resource) for parent close protection and cancellation checks.
No unsent text enters history/storage. Parent preserves draft on full navigation;
explicit Close asks before discard, while reload uses beforeunload protection.

Perspectives has no supported type or numeric count: its indicator opens the
existing unavailable explanation. New-item numeric count likewise stays unavailable
unless supplied by an actual supported contract; activity time is labelled only as
activity time. Files count is loaded selected files with partial/page wording.
Parent's nonmodal expansion keeps main work row operable, focuses the expanded
card deliberately, and restores the puck on collapse without trapping main focus.

Fixture only: sanctioned A/B/C setup, source posts/files, historical reply and Work
records with truthful statuses. Runtime allowlist for exact fixture message/create
endpoints, strict identity/body/path checks, no dispatch, credentials or method
override forwarding. Main and mini sends/create exercised only on disposable data.
One exact-commit build, focused unit/boundary checks, Windows Edge headless main/mini
coexistence + send/reply/history + indicators + management/create smoke; commands
and passed/failed/skipped/error counts recorded. Durable preview armed with
arm_detached before hidden launch; verify actual report and running URL.

TEST read-only investigation: persistent test/integration currently ceb306a2;
candidate base lacks 12 commits from its latest branch. Prepare cumulative merge
in own workspace and require candidate..serving count zero before any deployment.
Environment status currently cannot match the live front/interface to a release;
carrier must reconcile actual serving identity and coordination before a switch.
No TEST mutation/restart under this task until the grant/lease path is settled;
no DAY-TO-DAY deploy/restart. Do not touch another agent's held paths/processes.
