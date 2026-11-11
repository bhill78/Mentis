param(
  [switch]$DryRun,         # every prerequisite, then stop: nothing stopped or changed
  [switch]$RollbackOnly,   # put the application back now; the Brain is never restored
  [switch]$Rehearse,       # everything below against C:\Work\Mentis-Test-Server\r2-release, never the live server
  [switch]$FailAfterStart, # rehearsal only: fail once the new pair answers (after the checks), to run the rollback for real
  [string]$RehearsalName = 'rehearsal',
  # The exact release commit: the tip of release/dayday-modernize in C:\Work\Mentis-wt\modernize,
  # descending from the serving cbfabaa. NOT on main (it keeps Quiet Chat round 5).
  [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$Target,
  # The exact MARS commit and the SHA-256 prepare.ps1 pinned for releases\modernize-<sha12>\mars.exe.
  [Parameter(Mandatory = $true)][ValidatePattern('^[0-9a-f]{40}$')][string]$MarsCommit,
  [Parameter(Mandatory = $true)][ValidatePattern('^[0-9A-F]{64}$')][string]$MarsHash
)

# Modernize release (round 2, O1). Adapted from eff-release-cbfabaa\deploy.ps1 (itself carrying the
# agy attempt-2 lessons: exit file removed before launch, commit polled, unfinished launch ended,
# rollback start retried, started detached through Win32_Process.Create, never from a session shell).
# What changed from that helper:
#   - Target/MARS are parameters, validated: Target = tip of the local candidate branch (fetched,
#     FETCH_HEAD must equal it) and descends from cbfabaa; MARS = the folder prepare.ps1 built from
#     `git archive <MarsCommit>`, its hash pinned in PROVENANCE.json, the commit descending from 4a92477.
#   - The Brain backup is BOUNDED (bounded_backup.py): SQLite online backup of corpus.db, artifacts/
#     hardlinked after each blob is hashed against its name, small dirs copied. ~0.33 GB, not ~3.8 GB.
#     The helper keeps at most $KeepBackups of ITS OWN backups (pre-modernize-*, marked by BACKUP.json)
#     and never deletes the earlier pre-* backups; it reports their count and size.
#   - After the smoke, the backup is restored into a temp folder, opened, quick_checked and counted,
#     and the temp restore deleted (outside the downtime; a failure there is reported, not rolled back).
#   - The Rust launcher stays the magnet-1c0c13a binary; the front is magnet-auth-63079a0 (round 4 C1:
#     the 1c0c13a front with Magnet activation's owner authentication; route table unchanged).
#     Rollback = cbfabaa + the magnet-1c0c13a front and launcher + MARS deleg-4a92477 + the retained
#     cbfabaa dist.
$ErrorActionPreference = 'Stop'
$Here = 'C:\Work\Mentis-workspace\day-to-day\modernize-release'
$Python = 'C:\Work\Mentis\.venv\Scripts\python.exe'
$OldMars = 'C:\Work\Mentis-workspace\day-to-day\releases\deleg-4a92477\mars.exe'
$OldMarsHash = '98E9BD91D8D906BF045B03D339365B4C7276C3B1CF145FFF187DB448D4BC4E87'
$OldMarsCommit = '4a92477135e0141b9bf0b1cd758388356cae3dc6'
$MarsDir = "C:\Work\Mentis-workspace\day-to-day\releases\modernize-$($MarsCommit.Substring(0,12))"
$Mars = Join-Path $MarsDir 'mars.exe'
$MarsRepo = 'C:\Work\MARS-wt\modernize'
# THE LOCAL WORKER'S INTERPRETER (MARS_LOCAL_PYTHON): Rust MARS runs the `local` worker with it;
# it holds only the pinned third-party packages (MARS requirements-local-worker.txt), the worker's
# source comes from the MARS binary. Set for the NEW pair only (the rollback pair runs as it did).
# Optional: missing or unable to import the SDK, it is not set, `local` reports itself unavailable
# with a reason, and Claude, Codex, Antigravity and Kimi are unaffected (none of them uses it).
$LocalPython = 'C:\Work\MARS-venv\Scripts\python.exe'
$script:LocalPythonUse = ''
$CandidateRepo = 'C:\Work\Mentis-wt\modernize'
$CandidateBranch = 'release/dayday-modernize'
$From = 'cbfabaa07a53d655a203521d10253a56baffd55a'
$CheckoutNow = 'cbfabaa07a53d655a203521d10253a56baffd55a'  # where the serving checkout sits
$OldRelease = 'C:\Work\Mentis-workspace\day-to-day\releases\magnet-1c0c13a'
# THE NEW PAIR'S FRONT (round 4, C1): magnet-auth-63079a0 = the front built from r4-magnet 63079a0, which
# carries the owner's Cookie/Authorization to Magnet activation's private steps, beside the 1c0c13a launcher
# copied byte for byte. The candidate's Python refuses activation without the owner's session, so it must
# run behind this front: behind the 1c0c13a front every activation fails closed (502), owner or not.
# The rollback pair stays exactly magnet-1c0c13a.
$Release = 'C:\Work\Mentis-workspace\day-to-day\releases\magnet-auth-63079a0'
$OldServerHash = 'DBEBC34396A0512A15EE7C379C509A02A9A1BF7B13D48AF7CB0696FDB388086C'
$OldLauncherHash = '53E0D5B5B70583A2BDE300AB0798163E6D7B3F33083918E02090FCA9276C0C2B'
$ServerHash = '18A14F902D481DBF6605F3A58ED89CF7DBD0D7C23DFD9E36E2DD5340BDE910F3'  # front built from r4-magnet 63079a0 (round 4 C1: Magnet activation needs the owner's session)
$LauncherHash = '53E0D5B5B70583A2BDE300AB0798163E6D7B3F33083918E02090FCA9276C0C2B'  # the magnet-1c0c13a launcher, copied byte for byte
$KeepBackups = 2
$SpareGb = 10
$MostHours = 24
$T7 = $Target.Substring(0, 7)

if ($Rehearse) {
  $Root = 'C:\Work\Mentis-Test-Server\r2-release'
  $Repo = "$Root\code"
  $Out = "$Root\$RehearsalName"
  $Brain = "$Root\brain"
  $BackupRoot = "$Root\backups"
  $RunDir = "$Root\run"
  $Work = "$Root\ws"
  $Port = 8861; $PrivatePort = 8862
  $Shortcut = "$Root\start-mentis.ps1"
  # The front's table, as on live (below).
  $RouteTable = Join-Path $Here 'route-table.json'
  # Rehearsal MARS is the candidate build for both pairs: the old MARS's own probe sessions are not
  # isolated from the owner's user-level `mentis` registration (fixed in the candidate), and a
  # rehearsal must not open sessions on DAY-TO-DAY. The old binary is still hash-checked.
  $LaunchOldMars = $Mars
} else {
  if ($FailAfterStart) { throw '-FailAfterStart is for a rehearsal only' }
  $Root = $Here
  $Repo = 'C:\Work\Mentis-dayday'
  $Out = "$Here\live"
  $Brain = "$env:LOCALAPPDATA\Mentis\Mark-IV\brain"
  $BackupRoot = 'C:\Work\Mentis-brains'
  $RunDir = "$env:LOCALAPPDATA\Mentis\run\8760"
  $Work = 'C:\Work\Mentis-workspace\day-to-day'
  $Port = 8760; $PrivatePort = 18760
  $Shortcut = "$env:LOCALAPPDATA\Mentis\Mark-IV\start-mentis.ps1"
  # The front's table (round 3 final, B3): the unchanged binary's own default plus
  # `GET /owner/login` -> Python, the owner's login page. Without it that address is Fluid's index.
  $RouteTable = Join-Path $Here 'route-table.json'
  $LaunchOldMars = $OldMars
}
$Backup = Join-Path $BackupRoot "pre-modernize-$T7-$(Get-Date -Format yyyyMMdd-HHmm)"
$RestoreCheck = Join-Path $BackupRoot "restore-check-modernize-tmp"
$Launcher = Join-Path $Release 'mentis-launch.exe'
$Front = Join-Path $Release 'mentis-server.exe'
$OldLauncher = Join-Path $OldRelease 'mentis-launch.exe'
$OldFront = Join-Path $OldRelease 'mentis-server.exe'
$Dist = Join-Path $Repo 'apps\fluid-web\dist'
$KeptDist = Join-Path $Here $(if ($Rehearse) { "$RehearsalName-dist-cbfabaa" } else { 'dist-cbfabaa' })
$RunCmd = Join-Path $Here $(if ($Rehearse) { "$RehearsalName-run-new.cmd" } else { "run-modernize-$T7.cmd" })
$RollbackCmd = Join-Path $Here $(if ($Rehearse) { "$RehearsalName-run-old.cmd" } else { 'run-rollback-cbfabaa.cmd' })
$OldShortcutCmd = 'C:\Work\Mentis-workspace\day-to-day\eff-release-cbfabaa\run-eff-cbfabaa.cmd'
$ShortcutBackup = "$Shortcut.pre-modernize-backup"
$Base = "http://127.0.0.1:$Port"
$Headers = @{ 'X-Mentis-Client' = '1' }
$LiveBrain = "$env:LOCALAPPDATA\Mentis\Mark-IV\brain"

$script:lines = [System.Collections.Generic.List[string]]::new()
$script:status = 'NOT DEPLOYED: no verdict was reached'
$script:stopped = $false
$script:shortcutMoved = $false
$script:launch = $null

function Log([string]$Message) {
  $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $Message"
  Add-Content -LiteralPath (Join-Path $Out 'deploy.log') -Value $line -Encoding utf8
  $script:lines.Add("- $line")
}

function Git([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { $result = & git.exe -C $Repo @Arguments 2>&1; $code = $LASTEXITCODE }
  finally { $ErrorActionPreference = $old }
  if ($code -ne 0) { throw "git $($Arguments -join ' ') failed: $($result | Out-String)" }
  ($result | Out-String).Trim()
}

function Py([string]$Script, [string[]]$Arguments) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try { $result = & $Python -I (Join-Path $Here $Script) @Arguments 2>&1; $code = $LASTEXITCODE }
  finally { $ErrorActionPreference = $old }
  $text = ($result | Out-String).Trim()
  if ($code -ne 0) { throw "$Script $($Arguments -join ' ') exit ${code}: $text" }
  $text
}

function Get-Json([string]$Path, [int]$Timeout = 60) {
  Invoke-RestMethod -Headers $Headers -Uri "$Base$Path" -TimeoutSec $Timeout
}

function ServingCommit { try { (Get-Json '/api/server' 15).code.commit } catch { $null } }

function Listener([int]$OnPort) {
  Get-NetTCPConnection -LocalPort $OnPort -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
}

function Wait-PortFree([int]$OnPort, [int]$Seconds) {
  for ($i = 0; $i -lt $Seconds; $i++) {
    if (-not (Listener $OnPort)) { return $true }
    Start-Sleep 1
  }
  $false
}

function Counts([string]$Name, [string]$Of = $Brain) {
  $json = Py 'counts.py' @($Of)
  Set-Content -LiteralPath (Join-Path $Out $Name) -Value $json -Encoding utf8
  Log "counts $Name $json"
  $json | ConvertFrom-Json
}

function Write-RunCommand([string]$Path, [string]$UseLauncher, [string]$UseFront, [string]$UseMars, [string]$UseLocalPython = '', [bool]$NewPair = $false) {
  # The route table (`/owner/login` to Python) is the NEW pair's: the rollback pair is started
  # exactly as it was before the deploy (round-3 final review S5).
  $table = if ($RouteTable -and $NewPair) { " --route-table `"$RouteTable`"" } else { '' }
  @(
    '@echo off'
    'chcp 65001 >nul'
    'set "PYTHONIOENCODING=utf-8"'
    "set `"MARS_BACKENDS_FILE=$env:LOCALAPPDATA\mars\backends.json`""
    "set MENTIS_MARS_COMMAND=`"$UseMars`" stdio"
    $(if ($UseLocalPython) { "set `"MARS_LOCAL_PYTHON=$UseLocalPython`"" } else { 'rem MARS_LOCAL_PYTHON not set: the local runtime is unavailable, the others are unaffected' })
    "if not exist `"$RunDir`" mkdir `"$RunDir`""
    "del /q `"$RunDir\launcher.exit`" 2>nul"
    "cd /d `"$Repo`""
    "`"$UseLauncher`" `"$Brain`" --port $Port --private-port $PrivatePort --workspace `"$Work`" --python `"$Python`" --code `"$Repo`" --front `"$UseFront`" --dist `"$Dist`" --run-dir `"$RunDir`"$table 1>>`"$RunDir\launcher.log`" 2>&1"
    "echo %errorlevel% >`"$RunDir\launcher.exit`""
  ) | Set-Content -LiteralPath $Path -Encoding ascii
}

# What is still running, by both definitions. Empty means clear. A read that fails throws.
function Active-Runs {
  if ($Rehearse) { return @() }  # a copy holds open runs and no process behind them
  $working = Get-Json '/api/working' 60
  if ($working.why_not) { throw "/api/working could not say: $($working.why_not)" }
  $names = @(@($working.open) | Where-Object { $_ -and $_.held_here -and $_.state -ne 'runtime-ended' } |
             ForEach-Object { "$($_.name) ($($_.runtime))" })
  $activity = Get-Json '/fluid/api/home/activity?limit=64' 60
  if ([int]$activity.open -gt 0) { $names += "$([int]$activity.open) open in Fluid's activity" }
  $names
}

function Stop-Pair {
  $old = $ErrorActionPreference
  $ErrorActionPreference = 'Continue'
  try {
    # A launch this helper started may still be waiting on its front: end it, or it outlives the stop.
    if ($script:launch) {
      $running = Get-Process -Id $script:launch.Id -ErrorAction SilentlyContinue
      if ($running -and $running.StartTime -eq $script:launch.StartTime) {
        Log "stop unfinished launch $($script:launch.Id)"
        & taskkill.exe /PID $script:launch.Id /T /F 2>&1 | Out-Null
      }
      $script:launch = $null
    }
    $state = Join-Path $RunDir 'launch.json'
    if (Test-Path -LiteralPath $state) {
      $saved = Get-Content -Raw -LiteralPath $state | ConvertFrom-Json
      $stopLauncher = if ($saved.front.executable -like "$Release*") { $Launcher } else { $OldLauncher }
      $answer = & $stopLauncher stop --run-dir $RunDir --front 2>&1
      Log "launcher stop: $($answer | Out-String)"
      try {
        $parent = Get-Process -Id ([int]$saved.python.pid) -ErrorAction Stop
        if ($parent.StartTime.ToFileTimeUtc() -eq [long]$saved.python.start_time) {
          Log "stop Python tree $($saved.python.pid)"
          & taskkill.exe /PID $saved.python.pid /T /F 2>&1 | Out-Null
        }
      } catch { }
      Remove-Item -LiteralPath $state -Force -ErrorAction SilentlyContinue
    }
    foreach ($onPort in $Port, $PrivatePort) {
      $listen = Listener $onPort
      if ($listen) {
        Log "stop remaining pid $($listen.OwningProcess) on $onPort"
        & taskkill.exe /PID $listen.OwningProcess /T /F 2>&1 | Out-Null
      }
      if (-not (Wait-PortFree $onPort 30)) { throw "$onPort is still held 30 seconds after stop" }
    }
  } finally { $ErrorActionPreference = $old }
  Log "ports $Port and $PrivatePort are free"
}

function Start-Pair([string]$Command, [string]$ExpectedCommit) {
  # The last launch's exit file says nothing about this one, and cmd only removes it once it runs.
  $exit = Join-Path $RunDir 'launcher.exit'
  Remove-Item -LiteralPath $exit -Force -ErrorAction SilentlyContinue
  $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine = "cmd.exe /d /c `"$Command`""
    CurrentDirectory = $Repo
  }
  if ($created.ReturnValue -ne 0) { throw "Win32_Process.Create returned $($created.ReturnValue)" }
  Log "started $Command through Win32_Process.Create as cmd pid $($created.ProcessId)"
  $script:launch = Get-Process -Id $created.ProcessId -ErrorAction SilentlyContinue
  for ($i = 0; $i -lt 150; $i++) {
    if (Test-Path -LiteralPath $exit) { break }
    Start-Sleep 2
  }
  if (-not (Test-Path -LiteralPath $exit)) { throw 'launcher did not finish within 300 seconds' }
  $code = (Get-Content -Raw -LiteralPath $exit).Trim()
  if ($code -ne '0') {
    $tail = (Get-Content -LiteralPath (Join-Path $RunDir 'launcher.log') -Tail 20) -join ' | '
    throw "launcher exit ${code}: $tail"
  }
  $commit = $null
  for ($i = 0; $i -lt 30 -and -not $commit; $i++) {
    $commit = ServingCommit
    if (-not $commit) { Start-Sleep 2 }
  }
  Log "server reports commit $commit"
  if ($commit -ne $ExpectedCommit) { throw "server reports $commit, expected $ExpectedCommit" }
  foreach ($pair in @(@($Port, 'mentis-server'), @($PrivatePort, 'python'))) {
    $listen = Listener $pair[0]
    if (-not $listen) { throw "nothing listens on $($pair[0])" }
    $name = (Get-Process -Id $listen.OwningProcess).ProcessName
    Log "$($pair[0]) held by $name pid $($listen.OwningProcess)"
    if ($name -ne $pair[1]) { throw "$($pair[0]) held by $name, expected $($pair[1])" }
  }
}

function Timed-Get([string]$Path, [int]$Timeout = 180) {
  $watch = [Diagnostics.Stopwatch]::StartNew()
  try {
    $value = Get-Json $Path $Timeout
    $watch.Stop()
    Log "smoke $Path 200 $($watch.ElapsedMilliseconds) ms"
    return $value
  } catch {
    $watch.Stop()
    Log "smoke $Path FAILED after $($watch.ElapsedMilliseconds) ms: $($_.Exception.Message)"
    throw
  }
}

function Smoke([string]$ExpectedCommit, [switch]$AfterRollback) {
  # A run starting now is not a failure: paused work resumes when the server is back.
  $working = Timed-Get '/api/working'
  Log "open after restart: $(@(@($working.open) | Where-Object { $_ }).Count)"
  Timed-Get '/api/work' | Out-Null
  Timed-Get '/api/operational' | Out-Null
  Timed-Get '/fluid/api/home/work' | Out-Null
  Timed-Get '/fluid/api/home/needs-you' | Out-Null
  $execution = Timed-Get '/api/execution'
  $backends = @($execution.backends) + @($execution.runtimes) | Where-Object { $_ }
  $kinds = @($backends | ForEach-Object { if ($_.kind) { $_.kind } else { $_.id } })
  Log "MARS backends/runtimes: $($kinds -join ', ')"
  if (-not $backends) { throw 'MARS availability check returned no runtimes/backends' }
  if ($kinds -notcontains 'antigravity') { throw 'MARS does not list antigravity' }

  $conversation = Timed-Get '/fluid/api/collections/conversation?id=ent-84dadf9f66dd&limit=2'
  $posts = Timed-Get '/fluid/api/posts?ids=ent-978e8f0ea813&thread=1'
  $objects = Timed-Get '/fluid/api/objects?post=ent-978e8f0ea813'
  Log "live reads: conversation items=$(@($conversation.items).Count), posts=$(@($posts.posts).Count), objects=$(@($objects.objects).Count)"
  if (@($posts.posts).Count -lt 1) { throw 'the known post did not come back' }

  $fluid = Invoke-WebRequest -UseBasicParsing -Headers $Headers -Uri "$Base/fluid/" -TimeoutSec 60
  Log "smoke /fluid/ $($fluid.StatusCode) $($fluid.Content.Length) bytes"
  # FRONTEND = BACKEND: the bundle's identity names the commit the server reports, clean.
  $identity = Get-Content -Raw -LiteralPath (Join-Path $Dist 'build-identity.json') | ConvertFrom-Json
  Log "Fluid bundle commit=$($identity.commit) dirty=$($identity.dirty) untracked=$($identity.untracked)"
  if ($identity.commit -ne $ExpectedCommit -or $identity.dirty) { throw 'Fluid build identity is not the clean expected commit' }
  $serving = ServingCommit
  if ($serving -ne $identity.commit) { throw "server reports $serving but the bundle names $($identity.commit)" }

  $post = Counts $(if ($AfterRollback) { 'post-rollback-counts.json' } else { 'post-counts.json' })
  if ($post.quick_check -ne 'ok') { throw "corpus.db quick_check: $($post.quick_check)" }
  if ($script:pre) {
    foreach ($key in 'corpus_id', 'migrations') {
      if ("$($post.$key)" -ne "$($script:pre.$key)") { throw "$key changed: $($script:pre.$key) -> $($post.$key)" }
    }
    foreach ($key in 'entry', 'operational', 'delivery', 'artifacts_files') {
      if ([int64]$post.$key -lt [int64]$script:pre.$key) { throw "$key went down: $($script:pre.$key) -> $($post.$key)" }
    }
  }
  Log 'smoke and Brain integrity checks passed'
}

function Rehearsal-Checks([string]$Which) {
  # Rehearsal only, with the pair up: the candidate's own records (sessions with a host, op_key
  # contributions, leases, an outcome claim) are written by the candidate, read back by whichever
  # pair is up, and the front's Rust routes compared with Python's for the same request.
  if (-not $Rehearse) { return }
  if ($Which -eq 'new') {
    $said = Py 'exercise.py' @('write', $Base, $Brain, (Join-Path $Out 'exercise-write.json'))
    Log "exercise write (candidate): $($said -replace "`r?`n", ' | ')"
  }
  if (Test-Path -LiteralPath (Join-Path $Out 'exercise-write.json')) {
    $said = Py 'exercise.py' @('read', $Base, $Brain, (Join-Path $Out 'exercise-write.json'), (Join-Path $Out "exercise-read-$Which.json"))
    Log "exercise read ($Which pair): $(($said -split "`r?`n")[-1])"
  }
  $said = Py 'front_parity.py' @($Base, $RouteTable, (Join-Path $Out "front-parity-$Which.json"), '--conversation', 'ent-84dadf9f66dd', '--post', 'ent-978e8f0ea813')
  Log "front parity ($Which pair): $said"
}

function Restore-Shortcut {
  if (Test-Path -LiteralPath $ShortcutBackup) {
    Copy-Item -LiteralPath $ShortcutBackup -Destination $Shortcut -Force
    Log 'Start Mentis shortcut restored'
  }
}

function Put-Application-Back {
  Stop-Pair
  if ((Git rev-parse HEAD) -ne $From) { Git checkout -q -B release/dayday-main $From | Out-Null }
  if (Test-Path -LiteralPath $KeptDist) {
    if (Test-Path -LiteralPath $Dist) { Remove-Item -LiteralPath $Dist -Recurse -Force }
    Copy-Item -LiteralPath $KeptDist -Destination $Dist -Recurse
  }
  Write-RunCommand $RollbackCmd $OldLauncher $OldFront $LaunchOldMars
  try { Start-Pair $RollbackCmd $From }
  catch {
    Log "rollback start failed, once more after a pause: $($_.Exception.Message)"
    Stop-Pair
    Start-Sleep 15
    Start-Pair $RollbackCmd $From
  }
  Restore-Shortcut
  Smoke $From -AfterRollback
  try { Rehearsal-Checks 'old' } catch { Log "rehearsal checks on the old pair FAILED: $($_.Exception.Message)"; throw }
}

function Rollback([string]$Why) {
  Log "ROLLING BACK APPLICATION RELEASE: $Why"
  try {
    Put-Application-Back
    $script:status = "ROLLED BACK: serves $From again on MARS $LaunchOldMars with the retained cbfabaa bundle, and its smoke passed. Brain was not restored. Cause: $Why"
  } catch {
    $script:status = "ROLLBACK FAILED: $($_.Exception.Message). Original cause: $Why. Brain backup remains at $Backup"
  }
  Log $script:status
}

function Abort([string]$Why) { $script:status = "NOT DEPLOYED: $Why; nothing changed"; throw 'abort' }

function Prerequisites {
  $serving = ServingCommit
  if ($serving -ne $From) { Abort "server reports $serving rather than $From" }
  $head = Git rev-parse HEAD
  $branch = Git branch --show-current
  $dirty = Git status --porcelain
  Log "serving checkout head=$head branch=$branch dirty=$([bool]$dirty)"
  if (($head -ne $From -and $head -ne $CheckoutNow) -or $branch -ne 'release/dayday-main' -or $dirty) { Abort 'serving checkout moved or is dirty' }

  # The candidate is not on origin/main and is not pushed for this release: the local candidate
  # branch tip must be this exact commit, descending from what is serving.
  if (-not (Test-Path -LiteralPath $CandidateRepo)) { Abort "candidate repository missing: $CandidateRepo" }
  Git fetch -q $CandidateRepo $CandidateBranch | Out-Null
  $fetched = Git rev-parse FETCH_HEAD
  if ($fetched -ne $Target) { Abort "$CandidateRepo branch $CandidateBranch is at $fetched, not $Target" }
  & git.exe -C $Repo merge-base --is-ancestor $From $Target
  if ($LASTEXITCODE -ne 0) { Abort "$Target does not descend from $From" }

  # MARS: the folder prepare.ps1 made from exactly this commit, with exactly this hash.
  & git.exe -C $MarsRepo cat-file -e "$MarsCommit^{commit}"
  if ($LASTEXITCODE -ne 0) { Abort "MARS commit $MarsCommit is not in $MarsRepo" }
  & git.exe -C $MarsRepo merge-base --is-ancestor $OldMarsCommit $MarsCommit
  if ($LASTEXITCODE -ne 0) { Abort "MARS $MarsCommit does not descend from $OldMarsCommit" }
  $provenance = Join-Path $MarsDir 'PROVENANCE.json'
  if (-not (Test-Path -LiteralPath $provenance)) { Abort "MARS was not prepared: $provenance missing (run prepare.ps1)" }
  $prov = Get-Content -Raw -LiteralPath $provenance | ConvertFrom-Json
  if ($prov.commit -ne $MarsCommit -or $prov.sha256 -ne $MarsHash) { Abort "$provenance names $($prov.commit) / $($prov.sha256), not $MarsCommit / $MarsHash" }

  foreach ($path in $Python, $Mars, $OldMars, $OldLauncher, $OldFront, $Launcher, $Front,
                    (Join-Path $Here 'counts.py'), (Join-Path $Here 'bounded_backup.py'), $RouteTable) {
    if (-not (Test-Path -LiteralPath $path)) { Abort "prerequisite missing: $path" }
  }
  if (-not (Test-Path -LiteralPath $Shortcut)) { Abort "shortcut missing: $Shortcut" }
  # THE OWNER'S CREDENTIAL (owner authentication, round 3): without it every owner action is
  # refused after the cutover. A live deploy does not start without it; a rehearsal says so.
  $OwnerCredential = if ($env:MENTIS_OWNER_AUTH_FILE) { $env:MENTIS_OWNER_AUTH_FILE } else { "$Brain.owner-auth.json" }
  if (-not (Test-Path -LiteralPath $OwnerCredential)) {
    # from the candidate checkout: the serving checkout does not have mentis.owner_auth yet
    $how = "set it first at a console: cd /d `"$CandidateRepo`" && `"$Python`" -m mentis.owner_auth set --brain `"$Brain`" (a passphrase), or ... trust-local --brain `"$Brain`" (this installation trusts its local owner, no login)"
    if ($Rehearse) { Log "owner credential missing ($OwnerCredential): owner actions on the rehearsal pair would be refused; $how" }
    else { Abort "owner credential missing ($OwnerCredential): every owner action would be refused after the cutover; $how" }
  } else { Log "owner credential present: $OwnerCredential" }
  # Optional: never aborts. Imports what the worker needs, as MARS will run it (-P: no cwd on path).
  $script:LocalPythonUse = ''
  if (Test-Path -LiteralPath $LocalPython) {
    # through cmd, so the SDK's own stderr warnings never become a PowerShell error (Stop)
    & cmd.exe /d /c "`"$LocalPython`" -P -c `"import acp, openhands.sdk, openhands.tools`" >nul 2>nul"
    if ($LASTEXITCODE -eq 0) { $script:LocalPythonUse = $LocalPython; Log "local worker interpreter: $LocalPython (imports the SDK)" }
    else { Log "local worker interpreter $LocalPython cannot import the SDK: MARS_LOCAL_PYTHON not set, local unavailable, other runtimes unaffected" }
  } else { Log "local worker interpreter missing ($LocalPython): MARS_LOCAL_PYTHON not set, local unavailable, other runtimes unaffected" }
  foreach ($check in @(@($Front, $ServerHash), @($Launcher, $LauncherHash), @($OldFront, $OldServerHash), @($OldLauncher, $OldLauncherHash), @($Mars, $MarsHash), @($OldMars, $OldMarsHash))) {
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $check[0]).Hash -ne $check[1]) { Abort "$($check[0]) is not the expected binary" }
  }
  $launchState = Get-Content -Raw -LiteralPath (Join-Path $RunDir 'launch.json') | ConvertFrom-Json
  if ($launchState.front.executable -ne $OldFront -or $launchState.brain -ne $Brain) { Abort 'launcher state does not name the 1c0c13a front and this Brain' }
  if ((Listener $Port).OwningProcess -ne [int]$launchState.front.pid) { Abort "port $Port does not match the launcher state" }
  if (Test-Path -LiteralPath $Backup) { Abort "backup destination already exists: $Backup" }
  if (Test-Path -LiteralPath $RestoreCheck) { Abort "a restore check is left over at $RestoreCheck" }
  if (Test-Path -LiteralPath $KeptDist) { Abort "retained bundle destination already exists: $KeptDist" }

  # Room for a BOUNDED backup (corpus.db + small dirs; blobs are hardlinks), a restore check of the
  # same size, and a build, with something over; said before anything stops.
  $dbBytes = (Get-Item -LiteralPath (Join-Path $Brain 'corpus.db')).Length
  $walPath = Join-Path $Brain 'corpus.db-wal'
  if (Test-Path -LiteralPath $walPath) { $dbBytes += (Get-Item -LiteralPath $walPath).Length }
  $freeBytes = (Get-PSDrive C).Free
  $needBytes = 2 * ($dbBytes + 100MB) + ($SpareGb * 1GB)
  Log ("disk: free {0:N1} GB, corpus.db+wal {1:N2} GB, needed {2:N1} GB" -f ($freeBytes / 1GB), ($dbBytes / 1GB), ($needBytes / 1GB))
  if ($freeBytes -lt $needBytes) { Abort 'not enough free disk for the backup, its restore check and the build' }
  if (-not $script:reported -and (Test-Path -LiteralPath $BackupRoot)) {
    $script:reported = $true
    Log "earlier backups: $(Py 'bounded_backup.py' @('report', $BackupRoot))"
  }
}

function Rehearsal-Setup {
  # The rehearsal stands in for DAY-TO-DAY: the old pair serving cbfabaa on 8861/8862 from the
  # rehearsal checkout, a Start Mentis shortcut naming the cbfabaa run command, the route table file.
  New-Item -ItemType Directory -Force -Path $RunDir, $Work, $BackupRoot | Out-Null
  if (-not (Test-Path -LiteralPath $RouteTable)) { throw "missing $RouteTable (tools/release_modernize/route-table.json)" }
  if (-not (Test-Path -LiteralPath $Shortcut)) {
    Set-Content -LiteralPath $Shortcut -Encoding utf8 -Value "# rehearsal stand-in for start-mentis.ps1`n`$Launcher = '$OldShortcutCmd'"
  }
  # Only when nothing serves the rehearsal yet: then, and only then, stand the old pair up.
  if (-not (Listener $Port)) {
    if ((Git rev-parse HEAD) -ne $From) { Git checkout -q -B release/dayday-main $From | Out-Null }
    $identity = Get-Content -Raw -LiteralPath (Join-Path $Dist 'build-identity.json') | ConvertFrom-Json
    if ($identity.commit -ne $From -or $identity.dirty) { throw "rehearsal checkout's dist is not a clean $From build" }
    Write-RunCommand $RollbackCmd $OldLauncher $OldFront $LaunchOldMars
    Start-Pair $RollbackCmd $From
    $script:launch = $null
    Log "rehearsal: the old pair serves $From on $Port"
  }
}

New-Item -ItemType Directory -Force -Path $Out | Out-Null
Start-Transcript -Path (Join-Path $Out 'transcript.log') -Append | Out-Null
try {
  Log "deployment helper started pid=$PID DryRun=$DryRun RollbackOnly=$RollbackOnly Rehearse=$Rehearse FailAfterStart=$FailAfterStart Target=$Target MarsCommit=$MarsCommit"
  if ($Rehearse) {
    $script:liveBefore = Counts 'live-counts-before.json' $LiveBrain
    if (-not $RollbackOnly) { Rehearsal-Setup }
  }

  if ($RollbackOnly) {
    if (-not (Test-Path -LiteralPath $KeptDist)) { $script:status = 'NOT ROLLED BACK: the retained cbfabaa bundle is missing; nothing changed'; throw 'abort' }
    Rollback 'asked for with -RollbackOnly'
    throw 'abort'
  }

  Prerequisites
  if ($DryRun) {
    $now = @(Active-Runs)
    Log "active now: $($now.Count) $($now -join ', ')"
    $script:status = 'DRY RUN: all deployment prerequisites hold; nothing stopped or changed'
    throw 'abort'
  }

  $start = Get-Date
  # Back to waiting if a run starts during the last steps: nobody is here to arm this again.
  while ($true) {
    $quiet = 0; $failedReads = 0; $last = ''
    while ($quiet -lt 2) {
      try {
        $names = @(Active-Runs)
        $failedReads = 0
        if ($names.Count -gt 0) {
          $quiet = 0
          $said = $names -join ', '
          if ($said -ne $last) { Log "waiting for active runs: $said"; $last = $said }
        } else { $quiet++ }
      } catch {
        $quiet = 0; $failedReads++
        Log "active-run read failed: $($_.Exception.Message)"
        if ($failedReads -ge 10) { Abort 'active-run gate failed ten times' }
      }
      if (((Get-Date) - $start).TotalHours -gt $MostHours) { Abort "still busy after $MostHours hours" }
      if ($quiet -lt 2) { Start-Sleep 30 }
    }
    Log 'no active run in two checks 30 seconds apart'
    Prerequisites
    Write-RunCommand $RunCmd $Launcher $Front $Mars $script:LocalPythonUse $true
    Write-RunCommand $RollbackCmd $OldLauncher $OldFront $LaunchOldMars
    $script:pre = Counts 'pre-counts.json'
    Get-Json '/api/working' 60 | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $Out 'pre-working.json') -Encoding utf8
    $final = @(Active-Runs)
    if ($final.Count -eq 0) { break }
    Log "a run started at the last check: $($final -join ', '); waiting again"
    Start-Sleep 30
  }

  $script:held8790 = if ($Rehearse) { $null } else { (Listener 8790).OwningProcess }
  if (-not $Rehearse -and -not $script:held8790) { Log ':8790 was not listening before the stop' }
  $downAt = Get-Date
  # FROM THE MOMENT THE STOP BEGINS every failure leads to the rollback (review M5): a stop that
  # throws part way may already have taken DAY-TO-DAY down, so it is inside the try that rolls back,
  # and `stopped` is set before it, so the verdict says "after stop".
  $script:stopped = $true
  try {
    Stop-Pair
    # BOUNDED BACKUP of the stopped Brain: exact match required (nothing writes while stopped).
    Log "bounded backup of the stopped Brain to $Backup"
    $freeBefore = (Get-PSDrive C).Free
    $said = Py 'bounded_backup.py' @('backup', $Brain, $Backup, '--label', "pre-modernize-$T7")
    Set-Content -LiteralPath (Join-Path $Out 'backup.json') -Value $said -Encoding utf8
    $made = $said | ConvertFrom-Json
    Log ("backup made in {0} s: corpus.db {1:N0} MB, small {2:N0} MB, {3} blobs hardlinked ({4:N2} GB not copied), {5} copied; free space dropped {6:N0} MB" -f `
      $made.seconds, ($made.corpus_db_bytes / 1MB), ($made.small_copied_bytes / 1MB), $made.artifacts.linked, ($made.artifacts.linked_bytes / 1GB), $made.artifacts.copied, (($freeBefore - (Get-PSDrive C).Free) / 1MB))
    $stoppedCounts = Counts 'stopped-counts.json'
    foreach ($key in 'entry', 'operational', 'delivery', 'max_entry_rowid', 'migrations', 'artifacts_files', 'corpus_id') {
      if ("$($made.counts.$key)" -ne "$($stoppedCounts.$key)") { throw "the backup's $key is $($made.counts.$key), the Brain's $($stoppedCounts.$key)" }
    }
    if ($made.counts.quick_check -ne 'ok') { throw "the backup's quick_check: $($made.counts.quick_check)" }
    # corpus.db is the backup's own file (never a link): read-only is safe on it, and ONLY on it.
    Set-ItemProperty -LiteralPath (Join-Path $Backup 'corpus.db') -Name IsReadOnly -Value $true

    Copy-Item -LiteralPath $Dist -Destination $KeptDist -Recurse
    Log 'retained the cbfabaa Fluid bundle for application rollback'
    Git checkout -q -B release/dayday-main $Target | Out-Null
    Log "serving checkout moved to $(Git rev-parse HEAD)"
    Push-Location (Join-Path $Repo 'apps\fluid-web')
    try {
      & cmd.exe /d /c "npm ci > `"$Out\fluid-ci.log`" 2>&1"; $ciExit = $LASTEXITCODE
      Log "npm ci exit $ciExit"
      if ($ciExit -ne 0) { throw "npm ci exit $ciExit" }
      & cmd.exe /d /c "npm run build > `"$Out\fluid-build.log`" 2>&1"; $buildExit = $LASTEXITCODE
    } finally { Pop-Location }
    Log "Fluid build exit $buildExit"
    if ($buildExit -ne 0) { throw "Fluid build exit $buildExit" }
    $dirtyNow = Git status --porcelain
    if ($dirtyNow) { throw "the checkout is dirty after the build: $dirtyNow" }

    Start-Pair $RunCmd $Target
    Log ("downtime (stop to new pair answering): {0:N0} s" -f ((Get-Date) - $downAt).TotalSeconds)
    Smoke $Target
    Rehearsal-Checks 'new'
    if ($FailAfterStart) { throw 'rehearsal: failing once the new pair answers, as asked' }

    Copy-Item -LiteralPath $Shortcut -Destination $ShortcutBackup -Force
    $shortcutText = Get-Content -Raw -LiteralPath $Shortcut
    if (-not $shortcutText.Contains($OldShortcutCmd)) { throw 'Start Mentis shortcut does not name the current run command' }
    [IO.File]::WriteAllText($Shortcut, $shortcutText.Replace($OldShortcutCmd, $RunCmd))
    $script:shortcutMoved = $true
    Log "Start Mentis shortcut now names $RunCmd"
    $script:status = "DEPLOYED: serves $Target through the magnet-auth-63079a0 Rust front and MARS $MarsCommit; smoke and Brain integrity checks passed. Brain backup: $Backup."
  } catch { Rollback $_.Exception.Message }

  if ($script:stopped -and (Test-Path -LiteralPath $Backup)) {
    # Outside the downtime and outside the rollback: the backup is restored into a temp folder,
    # opened and checked, and the temp restore deleted; then this helper's retention bound.
    $restoreOk = $false
    try {
      $said = Py 'bounded_backup.py' @('verify-restore', $Backup, $RestoreCheck)
      Set-Content -LiteralPath (Join-Path $Out 'restore-check.json') -Value $said -Encoding utf8
      Log "restore check: $said"
      $restoreOk = $true
    } catch { Log "RESTORE CHECK FAILED: $($_.Exception.Message)"; $script:status += " The backup's restore check FAILED: see deploy.log." }
    # RETENTION ONLY AFTER A PASSED RESTORE CHECK (review M6): an older backup is never deleted to
    # make room for one that has not been shown to restore. bounded_backup.py retain also never
    # leaves fewer than two verified backups.
    if ($restoreOk) {
      try { Log "retention (keep $KeepBackups of this helper's backups): $(Py 'bounded_backup.py' @('retain', $BackupRoot, 'pre-modernize-', "$KeepBackups"))" }
      catch { Log "retention FAILED: $($_.Exception.Message)" }
    } else { Log 'retention skipped: the new backup did not pass its restore check; every older backup is kept' }
  }

  if ($script:status -like 'DEPLOYED*') {
    $afterCheck = Counts 'post-check-counts.json'
    if ($afterCheck.quick_check -ne 'ok') { $script:status += " corpus.db quick_check after the check: $($afterCheck.quick_check)." }
    if (-not $Rehearse) {
      $now8790 = (Listener 8790).OwningProcess
      Log ":8790 before pid $($script:held8790), now pid $now8790"
      if (-not $now8790 -or $now8790 -ne $script:held8790) { $script:status += " :8790 is not the process it was: before $($script:held8790), now $now8790." }
      else { $script:status += ' :8790 is still running, untouched.' }
    }
  }
} catch {
  if ($_.Exception.Message -ne 'abort') { $script:status = "NOT DEPLOYED: $($_.Exception.Message)$(if ($script:stopped) { ' after stop' })" }
} finally {
  if ($Rehearse -and $script:liveBefore) {
    try {
      $liveAfter = Counts 'live-counts-after.json' $LiveBrain
      Log "live Brain (read-only) before entry=$($script:liveBefore.entry) operational=$($script:liveBefore.operational); after entry=$($liveAfter.entry) operational=$($liveAfter.operational)"
    } catch { Log "live counts after: $($_.Exception.Message)" }
  }
  Log "verdict: $script:status"
  $report = @(
    "# $script:status"
    ''
    "cbfabaa -> $Target (modernize: completion claims, continuity, compiled rules, contributions, leases, session identity, outbox, + round 2), Quiet Chat round 5 kept; MARS $OldMarsCommit -> $MarsCommit ($Mars); front magnet-1c0c13a -> magnet-auth-63079a0 (Magnet activation needs the owner's session), launcher unchanged (magnet-1c0c13a)."
    "Deployment helper: $Here\deploy.ps1 (prepared by prepare.ps1)"
    "Rollback is application-only to $From with MARS $OldMars and the retained Fluid bundle $KeptDist`: rollback.cmd (deploy.ps1 -RollbackOnly). The Brain is never restored automatically; the bounded backup is $Backup (owner restore, server stopped: python -I bounded_backup.py restore <backup> <new folder>, then move it into place)."
    ''
    '## Log'
    ''
  ) + $script:lines
  Set-Content -LiteralPath (Join-Path $Out 'REPORT.md') -Value $report -Encoding utf8
  Stop-Transcript | Out-Null
}
