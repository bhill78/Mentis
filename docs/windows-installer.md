# The Windows installer

`Mentis-Setup-<version>-<commit12>.exe` installs the Mentis server and its built Fluid
for one Windows user, with its own Python. The target needs no Python, Node or Git.
It does not carry MARS: without one, the server and Fluid work and agents do not, and
the server says so (`mentis.cmd setup --mars "<command>"` names one).

## Build it

From the repository's virtual environment, on Windows, with Git, Node and network:

```
python tools/build_windows_installer.py --out <dir> [--commit <rev>]
```

It builds HEAD (or the commit named) from a fresh clone, so uncommitted changes are not
in it, and prints the installer's path, sha256 and size. The pinned Python and NSIS are
cached (`--cache`). The exe is also the package `mentis.cmd update` takes: there is one
thing to build and hand over.

## Prove it

```
python tools/prove_windows_installer.py <exe> --root <new-dir> --port <not-8760> --commit <sha>
    [--new <newer exe> --new-commit <sha>]
```

A real silent install, a new Brain, the server, Fluid in headless Edge, the MCP bridge,
a clean stop, attach and restart, installing again over a running install, then update
and rollback: the new commit with the same Brain, back, and again; the setup exe over
the install; the quick backup when nobody asked, the full one taken, verified and restored
when asked for, the wizard's question (clicked through by window messages, answered both
ways, No the default), and a full one failing with nothing changed; a damaged release repaired over itself and a damaged previous one staged
again; the new build's repair of the release `current` names, killed at each point inside
it and with its final replace really failing (the file held open), `start` refusing and
launching nothing until the exe has finished it; four packages refused with the server still answering; a new release that will
not start and one that fails its health check, each restored; running work waited for
and the update abandoned; something else holding the Brain open; a kill at every step of
an update, in a rollback, while switching back and from outside; a kill past the switch and
the new release then damaged, which is not committed; real additive and
breaking Brain migrations, the rollback they allow or refuse, and what happens when one
goes wrong past the point of no return; then an uninstall with the server running and
one with `mentis.cmd` broken, all under `--root`. Without `--new`, the newer build is this one stamped with another commit.
The broken and migrating packages are the build's stage changed and packed again, so
`work-<commit12>\` must still be beside the exe. It refuses port 8760 and refuses to run
if this user has an install. It does not touch another Brain or server.

The answer is one JSON object: `ok`, `failed`, `not_run` and every step. A step that could
not run, such as the browser check on a machine with no Edge, is listed under `not_run`,
does not stop the rest, and leaves `ok` false and the exit status 1: what it would have
shown has not been shown.

## What keeps it working

```
python -m pytest tests/test_windows_installer.py -m "not installer" -q   # six minutes
python -m pytest tests/test_windows_installer.py -m installer -q         # fifteen: build and prove
```

The first compiles and unpacks the NSIS script, and reads the source tree (`problems()` in the builder, also
`build_windows_installer.py --check`): a third-party import nothing locks, a standard
module the embeddable Python lacks, a `tools/` import the payload does not carry, a pin
changed without `--relock`, a payload source that has gone, a server flag `mentis.web`
no longer takes, a command or route update depends on that has gone. It also runs update
and rollback for real against a two-process stand-in: declared stop and start order, every
failure and a kill at every step. Run the second before a release, and after changing
packaging, dependencies, how the server starts or how it answers `/api/server`.

## Changing what it carries or starts

`tools/installer/manifest.json` is the one place:

- `builds`: what to run in the clone before staging.
- `payload`: source path to install path, under `app/`, laid out as a checkout is.
- `ports`: named ports, as offsets from the install's port.
- `launch`: what to start, in order, stopped in reverse, each with what it answers on.
- `identity`, `working`, `health`: what update asks the public port. `identity` must say
  this release's commit and this Brain (`/api/server`'s `release` and `corpus`).

A new process, such as a Rust front that owns the public port and forwards to Python
on a private one, takes a `builds` row, a `payload` row, a `ports` row and a `launch`
row, with Python's row moved to the new port name. No code changes. A row can name a
file in its release as `{release}\app\...`. Update and rollback start each release from
its own launcher and its own manifest, so the two can differ.

`tools/installer/requirements.lock` is generated (`--relock`), from `pyproject.toml` at
the versions the environment running it tests with. `tools/installer/lock.json` pins
Python and NSIS.

## The install

`%LOCALAPPDATA%\Programs\Mentis` by default, without elevation, registered as
`MentisServer`, so it cannot replace an install of Mark IV's rc installers.

```
<install>\
  mentis.cmd, uninstall.exe
  releases\<version>+<commit12>\   runtime\, app\: one build, whole, locked read-only
  state\                           current, previous, install.json, running.json, logs\,
                                   update.journal.json while an update runs, updates\
```

```
mentis.cmd setup [--brain DIR] [--owner @alias] [--attach] [--port N] [--workspace DIR] [--mars CMD]
mentis.cmd open | start | stop | status | verify | version
mentis.cmd update <Mentis-Setup-....exe> [--yes] [--drain-wait S] [--full-backup]
mentis.cmd update --resume
mentis.cmd rollback [--yes]
```

Setup is `python -m mentis.bootstrap`. A folder already holding a Brain needs
`--attach` and is checked with `--check` first. The Brain defaults to
`%USERPROFILE%\Mentis\brain`, and setup refuses one inside the install, because
uninstalling removes the install and leaves the Brain and workspace alone. The port
is the first free one from 8780. Start Menu has Mentis and Stop Mentis. Nothing starts
at login, and nothing watches or restarts the server. Logs are in `state\logs`.

Quiet: `Mentis-Setup-....exe /S [/FULLBACKUP] /D=<folder>`, last and unquoted, then
`mentis.cmd setup` with `--owner`. `uninstall.exe /S` returns at once and finishes in the background.

## Update and rollback

`mentis.cmd update <exe>` moves to another build, shows what it would do and asks (`--yes`
where nobody can be asked). The same exe double-clicked over the install is the same
update. `mentis.cmd rollback` goes back to the one before. `state\logs\update.log` has
the words; `state\updates\` has the journal of each.

Exit 0 done, 2 refused and nothing changed, 3 it did not happen (`reason` says aborted or
rolled_back, or not_repaired for a repair that could not finish, `previous_restored` whether
the old release is verified and healthy, `running` what answers now), 4 needs attention. One JSON object on stdout, whatever happened.

This is Mark IV's guarantee (`mentis/updater.py`, the reference), in less code because
each release here carries its own Python and needs no virtual environment:

| What it does | What it is for |
| --- | --- |
| Unpacks beside the running release, checks every file against the build's hash, runs its Python, then renames it into place and locks it read-only | Nothing the running server uses is touched until the new build is known whole; no later install or stray command changes what a server runs |
| Runs the rest in the new release's own launcher (`arrive` from the exe likewise, from `.incoming`) | A defect in the old release's update, or damage to the old release, cannot hold an install back |
| One update at a time (`state\update.lock`) | Two would race over the same journal and server |
| Plan first: what migrations run, whether going back stays possible, whether it is breaking | The person decides knowing; a program says `--yes` |
| Refuses before anything if the Brain has problems, has no ledger, was opened by a pre-ledger release, or the new release cannot read it | Never starts code on a Brain it cannot read |
| Waits for running work through `/api/working`, up to `--drain-wait` (10 minutes); if it will not finish, the update is abandoned and the server left running | An update does not kill somebody's run |
| Stops every declared process in reverse order, and confirms the Brain's open lock is free | Nothing still has the Brain open when it is migrated or the code changes |
| A backup every time, then verify-backup: the quick one (`local-recovery`), or full (`--portable`) if it was asked for. Either way before the Brain is migrated; what failing means is below | There is something to restore from, and it is known to be usable |
| `mentis.migrate --apply` by the new release, one transaction | The only thing that changes the Brain; the commit point C1 |
| `state\current` replaced atomically after the release is re-hashed | The commit point C2; a kill during the switch leaves it naming a release just checked whole |
| The new release re-hashed, `mentis.brain verify` (rebuild-derived when missing derived indexes are the only problem), start, then `identity` names this commit and this Brain and every `health` URL answers, then re-hashed before the update is called done | "Running" is checked, not assumed, and an answering server says nothing about the files it was started from |
| A journal at every step, fsynced; recovery reads the Brain's lock and ledger and `state\current`, not just the journal | A kill at any point finishes or undoes it from what actually happened; `start` and `open` do it first, so it cannot be started around |
| Before C1, the update did not happen: the staged release discarded when it can be, the old server restarted if it was running | Nothing the owner relies on has changed, so it is undone rather than pushed forward |
| After C1 and not switched: forward. The switch is redone | The owner approved it, and the Brain has moved |
| Unhealthy after C1 or C2, old release can read the Brain: switch back, start it, verify it and check it | The previous version is running again, with no record lost, and the words say so |
| Unhealthy, old release cannot read the Brain: stop everything, `state\needs-attention.json`, the restore-plan command said. Never a restore | Restoring discards records, so only a person does it; `update --resume` then goes back |
| A release's files re-hashed before it is switched back to or restarted by an undo | A damaged old release is never trusted, never called healthy |
| Recovery past the switch hashes the new release too, whichever state a kill left the journal in. Damaged, it takes the failure path above, from `update --resume` and from inside `start` and `open`: switch back, or needs attention | A release damaged after a kill is never started, resumed into or reported as the update having worked |
| `start` and `open` re-hash the current release before anything else, after recovering any unfinished update, and `setup` before it runs anything. A damaged release gets: nothing started, nothing new in `running.json`, a non-zero exit, the files named and that its setup exe repairs them. It is said even with a server already running, which is left alone (`stop` stops it) | Damaged code is not launched, and a damaged install never answers "already running" as if all were well (Mark IV's `start` does the same) |
| A damaged release staged again from its package is repaired in its place once the package verifies: copied whole to `<name>.damaged-<stamp>`, never deleted, then each file that differs replaced atomically; the same for the setup exe over itself, which otherwise leaves a whole release alone | A person can still see what went wrong, and the folder `state\current` may name never goes away |
| `rollback` is the same transaction with no migration, refused when the previous release cannot read the Brain | Going back carries the same guarantees, and never starts old code on a Brain it cannot read |
| `needs attention`, resumed with nothing serving: the new release again if it is whole, then the old one if it can read the Brain | A repaired install finishes what the owner approved; a failure then switches back as any failure does |

A repair cannot move the folder: Windows has no way to swap one folder for another in one
step, so a rename and a replace would leave a moment with nothing there. So the folder stays
and only files change, each in one step. This makes a missing release impossible, under a
kill or a failed file operation at any point of a repair: `state\current` and
`state\previous` name a folder that is there, holding every file it held, each as it was or
right. It does not make the release whole at every instant. Until a repair finishes, the
release is still damaged, by no more than it was: `mentis.cmd verify` says which files, and
`start` and `open` refuse it. Running the same setup exe again finishes the repair, and that
is the only way to finish it: `start` and `update --resume` have no package to repair from.
A repair that cannot finish, because something holds a file, exits 3 and says so; other files
may already have been replaced. A copy that cannot be made aside refuses with nothing replaced.

Recovery's exits, each with what it does about a damaged new release:

| Exit from `_recover` | With the new release damaged |
| --- | --- |
| Past C2, up to SWITCHED: `_step_healthy`, whether it would start the release or found it serving | Not started; switched back or needs attention |
| HEALTHY, which goes straight to COMMITTED | Not committed; switched back or needs attention |
| COMMITTED, where only archiving the journal was left | Not reported done; switched back or needs attention. The update was healthy when it reached this, and the journal is still there, so it is a failure of the same update, rather than a success with damage left for `start` to find |
| Past C1, not switched | The switch's own hash refuses it; switched back or needs attention |
| ROLLING_BACK | The target is the old release, hashed first; needs attention if damaged |
| Before C1 | The new release is not used; the old one is hashed before it is restarted |
| NEEDS_ATTENTION, `resolved` or retried | Resolved only if whole and healthy; retried only if whole, and then through the steps above |
| No journal | Says there is nothing to resume, and starts nothing |
| Neither release whole (`_resume`) | Exit 4, nothing started; the setup exe of either makes it whole, and the journal stays |

The check still runs inside the release it checks, so all of this is as far as a launcher
can go. Recovery runs from whichever named release is whole, and a `from` release built
before this check has the old recovery in it: it starts a damaged new release and commits.
This limit is the same as for `start`, below.

The check runs in the release it checks. If the damage is to the launcher or the Python
itself, `mentis.cmd` may not run at all, or may do nothing, until the exe has repaired it, and
the files are checked against that release's own `FILES.json`, which nothing checks. A release
built before this check keeps its own `start`, which does not re-hash. An update's or a
rollback's own restart (`start --in-update`) does not re-hash either: that restart's checks
are the table's above, and what they find is an outcome of the update, not a refusal.

As in Mark IV, no release is removed except one an update staged and then abandoned: a
release is about 100 MB and they add up, until somebody deletes one by hand (never
current or previous). A release that was switched back from is kept.

Migrations only move forward. Rollback over an additive migration leaves the Brain
migrated, and the older code reads it, as the open check allows. Backups are kept beside
the Brain (`<brain's parent>\backups`), and neither update nor uninstall removes one. Nothing
removes them until somebody prunes them (`python -m mentis.backups prune`, a dry run unless
`--confirm`): one more stays with each update and each rollback, and a full one is about the
size of the Brain.

## The full backup

An update takes the quick backup unless a full one is asked for, for people and for `--yes`
and `/S` alike: `mentis.cmd update --full-backup`, the setup exe's `/FULLBACKUP`, or Yes in the
wizard. It may need disk space comparable to the Brain's size, every time. A person in the
wizard is asked once, on an update only, after going ahead, with the size and where it goes:
No is the default button. `rollback` has no such option and takes the quick one.

| Route | Backup |
| --- | --- |
| `mentis.cmd update <exe>`, with or without `--yes` | quick |
| `mentis.cmd update <exe> --full-backup`, with or without `--yes` | full |
| Setup exe `/S` | quick |
| Setup exe `/S /FULLBACKUP` | full |
| Wizard, No (the default button) | quick |
| Wizard, Yes | full |
| Wizard with `/FULLBACKUP` | full, not asked |
| `mentis.cmd rollback` | quick |

| | Full (`portable`) | Quick (`local-recovery`) |
| --- | --- | --- |
| `corpus.db`, by SQLite's backup API | yes | yes |
| `instances\`, `mentis-corpus.json`, `presentation\` | yes | yes |
| Every stored file a non-purged Admission names | copied | listed by digest and size, not copied |
| Every other stored file in `artifacts\`, named by nothing in the record | copied | no |
| Usable if the Brain's folder is lost | yes | no |

It goes in `<brain's parent>\backups\<corpus id>\<time>-portable`, and neither update nor
uninstall removes it. If `<corpus id>`'s folder resolves inside the install, following a
junction at any level and whether or not it exists yet, an update that asked for it is
refused before anything changes. So it is if the Brain cannot say its corpus id, as where it
would go cannot then be told. The location is looked at only when a full backup is asked
for: the quick one goes where it always went. In that case the wizard does not ask: what it
shows before Go ahead says that no full backup can be offered, and why, and that the update
takes the quick one.

A full backup's verify-backup must pass, by a separate command, before the migration. Any
failure, a full disk included, stops the update before C1: nothing was migrated or switched, the staged
release is discarded, and the old server is restarted. The answer's `reason` is `aborted`.
What a failed one leaves: a backup refused by its own checks removes itself. Otherwise,
as on a full disk, what is left is `<time>-portable.partial`, which the update removes and
says so, because the old server needs that room to come back. If it cannot, it says that.
A complete backup that verify-backup then refuses is left where it is, as retention counts
only usable ones. A kill during the backup leaves its `.partial`: it never reads as a
backup (verify-backup says it was never completed, and retention does not count it), the
next update does not remove it. `python -m mentis.backups prune <brain> --confirm` does
once it is 30 days old, and a person can at any time.

The answer says which was taken (`full_backup`, `backup`, `backup_kind`), and so do the
words and the journal under `state\updates\`. The choice is recorded when the update is
approved. A resumed update takes no second backup, and keeps what the journal says.

A build from main up to 1c55e9f has no such flag: its `mentis.cmd update --full-backup` is
refused by its own parser. Updating from such a build takes the quick backup, or the full one
by the new setup exe's `/FULLBACKUP` or its wizard, as those run the new release's launcher.
Updating to one takes that release's quick backup.

`--full-backup` to such a build is refused by that build's parser (`unrecognized arguments:
--full-backup`). The Brain, the releases, what is current and the running server are as they
were, and a release staged for it is removed; `state\logs\update.log` has its line and
`state\update.lock` exists, as after any refusal. The answer is `refused`, but with `--yes` it
reads like a crash and does not say nothing changed: reason `crashed`, "the update ended with
exit 2 and gave no result". Without `--yes` it says "<release> did not answer (exit 2). Nothing
was changed."

The development commits 4ba5497, 724c52a and 6163dae took a full backup unless declined. They
were never released. An update to one would still do that without being asked, and 4ba5497's
and 724c52a's leave out the stored files nothing names.

Nothing ever restores a Brain from any of this, however the update fails and whatever
backup exists. A restore discards records, so only a person does it:
`python -m mentis.brain restore-plan <brain> <backup>`, then `restore` with its digest.

A full backup holds every stored file, each hashed against its name when it is taken, when
it is verified and when it is restored. One that fails in the backup makes the backup
unusable. `BACKUP.json` lists the ones the record names in `stored_files` and the others in
`unnamed_stored_files`, and verify-backup reports anything in the backup's store it lists in
neither. A backup taken before unnamed files were carried has no such list; it still
verifies and restores, and brings back what it holds.

A restore into the Brain never deletes a stored file already there, as ever. A stored file
the backup holds unnamed and the Brain has purged since is left out of the restore, and the
plan says so (`unnamed_purged_since_backup`); one the backup's own record names comes back
with that record, as the plan's `purged_since_backup` warns. A restore to a new location has
no record of the purge to read, so a stored file the backup holds unnamed and the Brain has
purged since does come back there, and nothing says so. Those bytes are in the backup until
the backup is removed.

What a full backup leaves out, and says so in `purged_stored_files_left_out` and
`stored_files_not_carried`:

- Bytes only purged Admissions name, left behind if a purge died before removing them. A
  purge is the owner's decision, and a backup and restore does not undo it.
- A file in `artifacts\` that cannot be a copy of anything: an unnamed one that does not hash
  to its name, one not at the name of its content, or a write that never finished. It stays
  in the Brain, untouched, as evidence. The backup still goes ahead, and the update's words
  name it: the bytes it should hold are gone, nothing names it, and stopping would cost a
  person the backup of everything else. A damaged file the record names is
  different, and stops the backup.
- `derived\`: extractions and indexes, made again on demand.
- Locks, SQLite's `-wal` and `-shm` (the backup API includes their content), `.pytest_cache`,
  a stray empty `corpus.sqlite3`, and `.import-staged.zip`, a staged import not yet applied.

Measured on a copy of a real Brain, by the real commands: 7,323 stored files and 3.3 GB in the
store, of which the record names 7,305 and nothing names 18. None were purged-only and none
were left out. A full backup held all 7,323, verify-backup passed on it, and a restore to a new
location brought back all 7,323, each with the same hash as in the Brain, and
`mentis.brain verify` passed there.

Backups across this change were tried the same way, on the same Brain:

| Backup made by | Restored by | What came back |
| --- | --- | --- |
| The build before unnamed files were carried | This build | The 7,305 it holds, and verify passes. The 18 were never in it |
| This build | The build before | 7,305. It verifies and restores, and verify passes, but it leaves out the 18 and does not say so |
| Either build, quick | The other, over the Brain whose store it lists | Restored, and verify passes |

So a full backup needs this build or a later one to bring back what nothing names.

Outside the Brain, `state\install.json` and the workspace are not backed up.

## What the package checks establish

They establish integrity, and not who published the package. They catch a damaged or
truncated download and a release changed after it was stamped. They do not stop somebody
who hands over a different exe:

- The `.sha256` beside the exe is optional, and whoever can replace the exe can replace it too.
- `SETUP_MARK`, the setup exe's description in its version resource, can be copied into any exe.
- `/EXTRACT` runs the supplied exe to read it, so that exe has already run with this user's
  rights before `FILES.json` is checked. `FILES.json` itself comes from the same exe.

So run only a setup exe whose source you trust. Nothing here is signed or fetched over an
authenticated channel.

## Left out

Signing (so SmartScreen warns), other platforms, the Mark IV desktop shell (a normal
install does not need it: Fluid runs in the browser), bundling MARS, an icon or licence
page. A folder with the earlier single-release layout, which never shipped, is not
updated: uninstall it first. Update and rollback are in; of Mark IV's `mentis update`,
`--progress jsonl` (its desktop shell read that), `--from-repo`, `--wheels` and `--version`
are not: the package is the setup exe, which carries its wheels and says its version.
`update` replaces releases and `state\`, not `mentis.cmd` or `uninstall.exe`, so those stay
as first installed until the setup exe runs over the folder.

## What only a clean machine proves

The proof above scrubs PATH and the Python variables but runs on the build PC, so it
cannot show that nothing else on the machine was used, such as the Visual C++ runtime
the wheels load, or how SmartScreen treats an unsigned exe. For that, run the installer
on a Windows machine that never had Python, Node or Git; Mark IV's clean-machine kit
(`cleanproof`, plan `adm-06dbd34701bf`) is the model, though its evidence script reads
Mark IV's layout and would need changing. The proof clicks through the wizard's pages for
an update by window messages, on this PC; how they look, a first install's pages, and
SmartScreen are proved only by a person.
