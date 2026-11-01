# The Windows installer

`Mentis-Setup-<version>-<commit12>.exe` installs the Mentis server and its built Fluid
for one Windows user, with its own Python. The target needs no Python, Node or Git.
It does not carry MARS: without one, the server and Fluid work and agents do not, and
the server says so (`mentis.cmd setup --mars "<command>"` names one).

## Build it

From the repository's virtual environment, on Windows, with Git, Node and network:

```
python tools/build_windows_installer.py --out <dir>
```

It builds HEAD from a fresh clone, so uncommitted changes are not in it, and prints the
installer's path, sha256 and size. The pinned Python and NSIS are cached (`--cache`).

## Prove it

```
python tools/prove_windows_installer.py <exe> --root <new-dir> --port <not-8760> --commit <sha>
```

A real silent install, a new Brain, the server, Fluid in headless Edge, the MCP bridge,
a clean stop, attach and restart, and an uninstall with the server running, all under
`--root`. It refuses port 8760 and refuses to run if this user has an install. It does
not touch another Brain or server.

## What keeps it working

```
python -m pytest tests/test_windows_installer.py -q                # seconds
python -m pytest tests/test_windows_installer.py -m installer -q   # minutes: build and prove
```

The first reads the source tree (`problems()` in the builder, also
`build_windows_installer.py --check`): a third-party import nothing locks, a standard
module the embeddable Python lacks, a `tools/` import the payload does not carry, a pin
changed without `--relock`, a payload source that has gone, a server flag `mentis.web`
no longer takes. Run the second before a release, and after changing packaging,
dependencies or how the server starts.

## Changing what it carries or starts

`tools/installer/manifest.json` is the one place:

- `builds`: what to run in the clone before staging.
- `payload`: source path to install path, under `app/`, laid out as a checkout is.
- `ports`: named ports, as offsets from the install's port.
- `launch`: what to start, in order, stopped in reverse, each with what it answers on.

A new process, such as a Rust front that owns the public port and forwards to Python
on a private one, takes a `builds` row, a `payload` row, a `ports` row and a `launch`
row, with Python's row moved to the new port name. No code changes.

`tools/installer/requirements.lock` is generated (`--relock`), from `pyproject.toml` at
the versions the environment running it tests with. `tools/installer/lock.json` pins
Python and NSIS.

## The install

`%LOCALAPPDATA%\Programs\Mentis` by default, without elevation, registered as
`MentisServer`, so it cannot replace an install of Mark IV's rc installers.

```
mentis.cmd setup [--brain DIR] [--owner @alias] [--attach] [--port N] [--workspace DIR] [--mars CMD]
mentis.cmd open | start | stop | status | verify | version
```

Setup is `python -m mentis.bootstrap`. A folder already holding a Brain needs
`--attach` and is checked with `--check` first. The Brain defaults to
`%USERPROFILE%\Mentis\brain`, and setup refuses one inside the install, because
uninstalling removes the install and leaves the Brain and workspace alone. The port
is the first free one from 8780. Start Menu has Mentis and Stop Mentis. Nothing starts
at login, and nothing watches or restarts the server. Logs are in `state\logs`.

Quiet: `Mentis-Setup-....exe /S /D=<folder>`, last and unquoted, then `mentis.cmd setup`
with `--owner`. `uninstall.exe /S` returns at once and finishes in the background.

## Left out

Signing (so SmartScreen warns), updates (run the newer installer over the same folder:
it stops the server and replaces the code; there is no rollback or Brain migration
step), other platforms, the Mark IV desktop shell (a normal install does not need it:
Fluid runs in the browser), bundling MARS, an icon or licence page.

## What only a clean machine proves

The proof above scrubs PATH and the Python variables but runs on the build PC, so it
cannot show that nothing else on the machine was used, such as the Visual C++ runtime
the wheels load, or how SmartScreen treats an unsigned exe. For that, run the installer
on a Windows machine that never had Python, Node or Git; Mark IV's clean-machine kit
(`cleanproof`, plan `adm-06dbd34701bf`) is the model, though its evidence script reads
Mark IV's layout and would need changing. The wizard's own pages are also proved only
by a person clicking through them: the proof uses `/S`.
