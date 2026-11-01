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
the install; a damaged release repaired over itself and a damaged previous one staged
again; the new build's repair of the release `current` names, killed at each point inside
it and with its final replace really failing (the file held open); four packages refused with the server still answering; a new release that will
not start and one that fails its health check, each restored; running work waited for
and the update abandoned; something else holding the Brain open; a kill at every step of
an update, in a rollback, while switching back and from outside; real additive and
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
mentis.cmd update <Mentis-Setup-....exe> [--yes] [--drain-wait S]
mentis.cmd update --resume
mentis.cmd rollback [--yes]
```

Setup is `python -m mentis.bootstrap`. A folder already holding a Brain needs
`--attach` and is checked with `--check` first. The Brain defaults to
`%USERPROFILE%\Mentis\brain`, and setup refuses one inside the install, because
uninstalling removes the install and leaves the Brain and workspace alone. The port
is the first free one from 8780. Start Menu has Mentis and Stop Mentis. Nothing starts
at login, and nothing watches or restarts the server. Logs are in `state\logs`.

Quiet: `Mentis-Setup-....exe /S /D=<folder>`, last and unquoted, then `mentis.cmd setup`
with `--owner`. `uninstall.exe /S` returns at once and finishes in the background.

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
| `mentis.brain backup`, then verify-backup, every time | There is something to restore from, and it is known to be usable |
| `mentis.migrate --apply` by the new release, one transaction | The only thing that changes the Brain; the commit point C1 |
| `state\current` replaced atomically after the release is re-hashed | The commit point C2; a kill during the switch leaves it naming a release just checked whole |
| `mentis.brain verify` (rebuild-derived when missing derived indexes are the only problem), start, then `identity` names this commit and this Brain and every `health` URL answers | "Running" is checked, not assumed |
| A journal at every step, fsynced; recovery reads the Brain's lock and ledger and `state\current`, not just the journal | A kill at any point finishes or undoes it from what actually happened; `start` and `open` do it first, so it cannot be started around |
| Before C1, the update did not happen: the staged release discarded when it can be, the old server restarted if it was running | Nothing the owner relies on has changed, so it is undone rather than pushed forward |
| After C1 and not switched: forward. The switch is redone | The owner approved it, and the Brain has moved |
| Unhealthy after C1 or C2, old release can read the Brain: switch back, start it, verify it and check it | The previous version is running again, with no record lost, and the words say so |
| Unhealthy, old release cannot read the Brain: stop everything, `state\needs-attention.json`, the restore-plan command said. Never a restore | Restoring discards records, so only a person does it; `update --resume` then goes back |
| A release's files re-hashed before it is switched back to or restarted | A damaged old release is never trusted, never called healthy |
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
what they break stays broken. Running the same setup exe again finishes the repair, and that
is the only way to finish it: `start` and `update --resume` have no package to repair from.
If the damage is to the launcher or the Python itself, `mentis.cmd` cannot run until then.
A repair that cannot finish, because something holds a file, exits 3 and says so; other files
may already have been replaced. A copy that cannot be made aside refuses with nothing replaced.

As in Mark IV, no release is removed except one an update staged and then abandoned: a
release is about 100 MB and they add up, until somebody deletes one by hand (never
current or previous). A release that was switched back from is kept.

Migrations only move forward. Rollback over an additive migration leaves the Brain
migrated, and the older code reads it, as the open check allows. Backups are kept beside
the Brain (`<brain's parent>\backups`), and neither update nor uninstall removes one.

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
Mark IV's layout and would need changing. The wizard's own pages are also proved only
by a person clicking through them: the proof uses `/S`.
