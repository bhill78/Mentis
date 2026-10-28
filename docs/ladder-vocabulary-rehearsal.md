# Mentis — Ladder Vocabulary Repair and Migration Rehearsal

This document details the rehearsal of `tools/ladder_vocabulary.py` on a copy of the live
Brain (`C:\Work\Mentis-brains\rehearse-vocab`), the changes verified through the real agent bridge
and HTTP owner routes, and the exact runbook to apply this to the day-to-day Brain once the owner
approves.

---

## 1. Background

A four-runtime audit on 2026-10-28 found that the live Brain predated several Mark IV epistemic ladder
and governance decisions:
- Concluded Kinds (`finding`, `lesson`, `solution`, `hypothesis`) lacked `requires_basis: True` enforcement.
- `solution` Kind was missing entirely.
- `hypothesis` lacked `standing_apt`, `expects_falsifier`, and recordable structured fields (`limits`, `falsifier`).
- Relations `in-context`, `declines`, and `withdraws` were undefined, causing `in_context` outcomes,
  `withdraw_challenge`, and owner `decline` to fail on live data.
- Seven Mark IV candidates sat in the record as unestablished entries without adoption requests,
  leaving them invisible in `/api/ladder/adoption` and in `governed state=proposed`.

---

## 2. Rehearsal Results

Rehearsal was executed against server port **8797** serving `C:\Work\Mentis-brains\rehearse-vocab`
with owner participant `@brian` (`ent-5936369158a8`).

### 2.1 Definition Changes (11 Planned, 11 Applied)

All 11 changes are append-only definition updates or creations:

| # | Family | Name | Before | After | Approved Delta / Notes |
|---|---|---|---|---|---|
| 1 | Kind | `problem` | `standing_apt: None` | `standing_apt: False` | Concluded problem cannot stand on its own |
| 2 | Kind | `solution` | *(None - unseeded)* | `fields: ['text']`, `standing_apt: False`, `requires_basis: True`, `knowing: 'that'` | Shipped in seed, now established in Brain |
| 3 | Kind | `hypothesis` | `fields: ['text']`, `standing_apt: None`, `expects_falsifier: None`, `requires_basis: None` | `fields: ['text', 'limits', 'falsifier']`, `standing_apt: True`, `expects_falsifier: True`, `requires_basis: True` | Restores structured fields, falsifier expectation, and single owner adoption approval |
| 4 | Kind | `finding` | `requires_basis: None` | `requires_basis: True` | Basis required (extracted/derived link) |
| 5 | Kind | `outcome` | `fields: ['text', 'result']`, `standing_apt: None` | `fields: ['text', 'result', 'attempted']`, `standing_apt: False` | Adds `attempted` boolean; contextual evidence only |
| 6 | Kind | `lesson` | `fields: ['text']`, `requires_basis: None` | `fields: ['text', 'limits']`, `requires_basis: True` | Adds `limits` field; basis required |
| 7 | Kind | `rule` | `fields: ['text']` | `fields: ['text', 'about']` | Adds `about` for conflict/scope comparison |
| 8 | Kind | `decision` | `fields: ['text']` | `fields: ['text', 'about']` | Adds `about` for conflict/scope comparison |
| 9 | Relation | `in-context` | *(None - unseeded)* | `inverse: context-of`, `directed: True`, `substrate_role: None` | Links outcome to Turn/Conversation context |
| 10 | Relation | `declines` | *(None - unseeded)* | `inverse: declined-by`, `directed: True`, `substrate_role: None` | Records owner decline of adoption request |
| 11 | Relation | `withdraws` | *(None - unseeded)* | `inverse: withdrawn-by`, `directed: True`, `substrate_role: None` | Records challenger withdrawal of dispute |

### 2.2 Migrated Mark IV Candidates (7 Candidates)

All 7 candidates were migrated into explicit adoption requests (`proposes` links and `decision` asks)
in a dedicated "Adoption requests" conversation, attributed to their original proposers:

| # | Entry ID | Kind | Proposer | Proposer Alias | Replaces (Predecessor) | Generated Request | Generated Ask |
|---|---|---|---|---|---|---|---|
| 1 | `ent-fb893b2e57f9` | rule | `ent-3a5fb342dd6b` | `@Caretaker` | `ent-51af2e8f31e3` | `ent-f0acf57638b8` | `opr-d2974381af9d` |
| 2 | `ent-f08d1718838b` | rule | `ent-3a5fb342dd6b` | `@Caretaker` | `ent-51af2e8f31e3` | `ent-c78e68620f78` | `opr-dfd39e999376` |
| 3 | `ent-4f605a3242ca` | rule | `ent-5936369158a8` | `@brian` | *(None)* | `ent-3cb2b6aa16b2` | `opr-31eb06ab2e13` |
| 4 | `ent-0a911c467d21` | rule | `ent-3a5fb342dd6b` | `@Caretaker` | `ent-5608ed0ee75f` | `ent-6dc3f4550d54` | `opr-61f7943724ca` |
| 5 | `ent-1380fc5ea315` | rule | `ent-3a5fb342dd6b` | `@Caretaker` | `ent-5608ed0ee75f` | `ent-b2f8364df1b8` | `opr-d1e883d0f59c` |
| 6 | `ent-435237999a2c` | decision | `ent-3a5fb342dd6b` | `@Caretaker` | *(None)* | `ent-f494e3ded03c` | `opr-915ccaae03ec` |
| 7 | `ent-934f286ed804` | discipline | `ent-e5f6f7a35a41` | `@Atlas` | *(None)* | `ent-b66d2286394d` | `opr-b6b4fc964363` |

Skipped candidates: 0.

---

## 3. Runtime Verification Evidence

Verified using the real agent bridge (`tools/mcp_bridge.py --session antigravity --server http://127.0.0.1:8797`)
and HTTP owner routes (`X-Mentis-Client: 1`):

1. **`requires_basis` enforcement**:
   - `record_material finding` without basis -> refused (`NotPermitted: 'finding' declares requires_basis`).
   - `record_material finding` with basis `[turn]` -> accepted (`ent-152b784293cd`, `stands: False`).
   - `record_material lesson` without basis -> refused (`NotPermitted: 'lesson' declares requires_basis`).
   - `record_material lesson` with basis `[finding]` -> accepted (`ent-bf01b0a8c4cd`, `stands: False`).
   - `record_material solution` without basis -> refused (`NotPermitted: 'solution' declares requires_basis`).
   - `record_material solution` with basis `[finding]` -> accepted (`ent-bb1c8d11497e`, `stands: False`).

2. **Hypothesis with structured falsifier and limits**:
   - `record_material hypothesis` with `{text, limits, falsifier}` and basis -> accepted (`ent-da165735d207`, `stands: False`).
   - No refusal on `falsifier` or `limits` fields.

3. **Outcome with `in_context` and `outcome_of`**:
   - `record_material outcome` with `outcome_of=solution`, `in_context=turn`, `result="worked"`, `attempted=True` -> accepted (`ent-d5355f69470d`, `stands: False`).
   - `in-context` link written successfully.

4. **Challenge and withdrawal**:
   - `challenge target=finding` -> dispute link created (`ent-ea42750c41f5`).
   - `withdraw_challenge dispute=ent-ea42750c41f5` -> withdrawal link created (`ent-18b975b8b120`).

5. **Owner decline**:
   - `POST /api/entries/ent-bf01b0a8c4cd/request-adoption` -> opened adoption request (`ent-d3219a9833df`, ask `opr-547f6437ba2b`).
   - `POST /api/entries/ent-bf01b0a8c4cd/decline` -> successfully recorded `declines` link (`ent-74ce78c89037`), answered the ask.

6. **Queue visibility and attribution**:
   - `GET /api/ladder/adoption` returned all 7 migrated candidate cards, attributed to original proposers (`@Caretaker`, `@brian`, `@Atlas`).
   - MCP `governed state=proposed` returned all 7 candidate rows under `groups.proposed`.

7. **Supersession on adoption**:
   - Standing rule `ent-0e43bf39866b` verified standing before (`stands: True`).
   - `POST /api/entries/ent-1380fc5ea315/adopt` as owner with `replaces: ["ent-0e43bf39866b"]` -> succeeded.
   - Afterwards: `ent-0e43bf39866b` has `stands: False`, `superseded_by: ["ent-1380fc5ea315"]`.
   - In `governed state=history`, `ent-0e43bf39866b` appears in history.
   - In `governed state=standing`, `ent-1380fc5ea315` appears in standing.

8. **Non-regression of standing governance**:
   - Immediately following the repair, all 6 pre-existing standing rules (`ent-6121edbe2f8c`, `ent-08b6d3e67f54`, `ent-58aa9a229cac`, `ent-0e43bf39866b`, `ent-c98876588cbf`, `ent-8884b34d4596`) retained `stands: True`. Nothing stood before stopped standing because of the repair itself.

---

## 4. Runbook: Applying to the Day-to-Day Brain

When the owner approves applying this to the live day-to-day Brain:

### Step 1: Prepare and verify clean backup
Take a read-only copy of the live Brain using SQLite backup API:
```powershell
# Example: copy %LOCALAPPDATA%\Mentis\Mark-IV\brain to a staging copy
$LIVE = "$env:LOCALAPPDATA\Mentis\Mark-IV\brain"
$STAGE = "C:\Work\Mentis-brains\stage-day-to-day"
# Copy corpus.db (SQLite backup API from a mode=ro connection), mentis-corpus.json,
# presentation/, derived/, instances/ (and artifacts/ if file content must be readable)
```

### Step 2: Rehearse on the staging copy first
Start a development server against the staging copy on an ephemeral port (e.g. 8798):
```powershell
python -m mentis.web C:\Work\Mentis-brains\stage-day-to-day --port 8798 --workspace C:\Work\Mentis-workspace\stage
```
Run dry run and apply rehearsal:
```powershell
# Dry run
python tools/ladder_vocabulary.py --server http://127.0.0.1:8798 --dry-run --migrate-proposed

# Apply with owner participant ID (ent-5936369158a8 for @brian)
python tools/ladder_vocabulary.py --server http://127.0.0.1:8798 --apply --migrate-proposed --attributed-to ent-5936369158a8
```
Verify the output matches the expected 11 changes and 7 migrated candidates. Stop the staging server.

### Step 3: Apply to Day-to-Day Server
Only after the owner's day-to-day transition: the server holding DAY-TO-DAY must be the new
Mentis (this repository) serving the day-to-day Brain. Do NOT apply it through the Mark IV
release that served :8760 on 2026-10-28 — its code is not this repair's. The port below is
whatever the day-to-day server listens on; `--day-to-day` is required when it is 8760:
```powershell
python tools/ladder_vocabulary.py --server http://127.0.0.1:8760 --day-to-day --apply --migrate-proposed --attributed-to ent-5936369158a8
```

### Step 4: Post-Application Verification Checklist
Run the verification queries against the target server:
```powershell
# 1. Verify 0 pending changes remaining
python tools/ladder_vocabulary.py --server http://127.0.0.1:8760 --day-to-day --dry-run --migrate-proposed

# 2. Verify adoption queue lists 7 migrated cards
python -c "import urllib.request, json; req = urllib.request.Request('http://127.0.0.1:8760/api/ladder/adoption', headers={'X-Mentis-Client': '1'}); data = json.load(urllib.request.urlopen(req)); print('Queue cards:', len(data['requests']))"

# 3. Verify standing rules still stand
python -c "import urllib.request, json; req = urllib.request.Request('http://127.0.0.1:8760/api/server', headers={'X-Mentis-Client': '1'}); print(json.load(urllib.request.urlopen(req)))"
```
