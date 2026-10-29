# DAY-TO-DAY cutover: the new Mentis takes over the owner's Brain

**Prepared and rehearsed on 2026-10-29. Not performed.** It is run only with the
owner's explicit authorisation. Rehearsed twice on fresh copies of the live Brain,
artifacts included; the second run went through `cutover.ps1` in one pass in 23 s.

Live Brain: `%LOCALAPPDATA%\Mentis\Mark-IV\brain`. Owner Participant: `ent-5936369158a8`
(`@brian`). Mark IV's server: `:8760`, started by its own launcher from
`%LOCALAPPDATA%\Mentis\Mark-IV`.

## Before (nothing changes yet)

1. Decide the Persona revisions. Baseline v3 only *proposes* them; leave them proposed,
   or edit `mentis/bootstrap/baseline.json` first.
2. Make a **dedicated checkout** for the day-to-day server, separate from development
   clones: `git clone https://github.com/bhill78/Mentis C:\Work\Mentis-dayday`. Then
   `git -C C:\Work\Mentis-dayday checkout <the release commit>`, and build Fluid there
   (`apps\fluid-web`: `npm ci`, `npm run build`). Use `C:\Work\Mentis\.venv` or a venv of
   its own.
3. Note what is running: `Get-NetTCPConnection -LocalPort 8760 -State Listen`. Make sure
   no agent run is in flight; the Mark IV Home page shows them.

## Cutover

4. **Stop Mark IV's server** on :8760. If `Stop-Process` is refused, the server is
   elevated: stop it from an elevated prompt (`taskkill /PID <pid> /F`). Leave the
   Mark IV installation itself untouched.
5. **Back up the Brain**, while nothing holds it:
   `robocopy "%LOCALAPPDATA%\Mentis\Mark-IV\brain" "C:\Work\Mentis-brains\pre-cutover-<date>" /E /XD worktrees scratch /MT:8`.
   Confirm `corpus.db`, `mentis-corpus.json`, `presentation\`, `derived\` and
   `artifacts\` are present, with the same number of artifact files.
6. **Run the cutover** (repair, vocabulary, baseline v3, approved governance, declines),
   leaving the new server running:
   `powershell -File C:\Work\Mentis-dayday\docs\cutover\cutover.ps1 -Brain "%LOCALAPPDATA%\Mentis\Mark-IV\brain" -Port 8760 -DayToDay -Code C:\Work\Mentis-dayday -Leave`.
   Every step is idempotent. If one fails, fix the cause and run the script again.
7. **Re-point each CLI's `mentis` registration** at the new bridge, with Brain pinning.
   Copy each file aside first. Each entry becomes:
   `python -I C:\Work\Mentis-dayday\tools\mcp_bridge.py --session <runtime> --server http://127.0.0.1:8760 --brain "%LOCALAPPDATA%\Mentis\Mark-IV\brain"`.
   - Claude: `~/.claude.json` → `mcpServers.mentis`.
   - Codex: `~/.codex/config.toml` → `[mcp_servers.mentis]`.
   - Antigravity: `~/.gemini/config/mcp_config.json` → `mcpServers.mentis`.
   - Kimi: `~/.kimi-code/mcp.json` → `mcpServers.mentis`.
8. **Check**, from a new CLI session in each runtime:
   - `orient` reports the live Brain path;
   - `recall("Mark IV is the reference implementation")` returns the new rule;
   - Fluid's *Manage Brain → Rules & decisions* shows the seven rules In force;
   - `GET /api/context-cache` shows hits after a second `brief`;
   - a post from Fluid to an agent with Task Gravity runs through MARS, and its run
     details show Participant · Persona · runtime · Task Gravity.

## Rollback

The record is append-only, and the new Mentis keeps Brain format, record ids and
relations readable by Mark IV. So there are two ways back.

- **Keep what happened since the cutover (preferred):**
  1. Stop the new server.
  2. Restore the CLI registration files saved in step 7.
  3. Start Mark IV's server again with its own launcher.

  Mark IV reads the Brain as the new Mentis left it, including the new definitions and
  governance. Mark IV does not apply Governance Condensation levels (it ignores
  `delivery` on a placement) and has no `take_up`. Both degrade to Mark IV behaviour:
  full delivery, and no session pickup.
- **Return to exactly the pre-cutover Brain:**
  1. Stop the new server.
  2. Move the migrated Brain aside, never delete it:
     `ren "%LOCALAPPDATA%\Mentis\Mark-IV\brain" brain.after-cutover`.
  3. Copy the step-5 backup back to `%LOCALAPPDATA%\Mentis\Mark-IV\brain`.
  4. Restore the registration files and start Mark IV.

  Everything recorded after the cutover then exists only in `brain.after-cutover`.

## What the cutover writes

All of it is through the owner's doors, append-only:
- 11 ladder definition changes, and 7 Mark IV candidates opened as adoption requests;
- 2 definition versions (Discipline, Workflow);
- baseline v3: the Discipline and Workflow established; proposals for Builder,
  Independent Reviewer and the general rules;
- the seven approved rules: six by `establish-replacement`, one new;
- placements at their delivery levels;
- two declines.

The decisions are in `governance-2026-10-29.json`.
