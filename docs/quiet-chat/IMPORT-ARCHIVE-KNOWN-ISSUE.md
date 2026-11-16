# Import Archive: a staged archive is never applied and cannot be discarded

Recorded 2026-11-16 at the close of Manage Brain. Open; not fixed. Not part of
Manage Brain and older than it (Manage Brain reuses `ImportArchiveTab` as is).

## What happens

1. Import Archive verifies an archive and writes it to `<brain>/.import-staged.zip`
   (`mentis/web/exchange_import.py`, `stage_archive`).
2. The server answers "Archive verified and staged for application on next
   restart", and the interface repeats it ("Import Staged for Next Restart",
   `apps/fluid-web/src/fluid/governance/ImportArchiveTab.tsx`).
3. Nothing reads `.import-staged.zip` at start. No code outside
   `exchange_import.py` and the interface names the file. A restart applies
   nothing, and the banner stays.
4. The staged archive cannot be discarded from the interface. `exchange_import.py`
   has `delete_staged` behind `DELETE /api/exchange/import/stage`, but the HTTP
   server has no DELETE handler, so the route is unreachable. The only way to
   remove the file today is by hand in the Brain folder.

## Consequences

- The interface promises an effect that does not occur.
- A staged archive sits in the Brain root indefinitely.

## To decide when this is taken up

- Whether import should be applied at restart at all, or applied as an explicit
  owner act while running (and what the migration/backup step is).
- Until then, whether staging should be offered, or the wording changed to say
  the archive is only verified and held.
- A reachable discard.
