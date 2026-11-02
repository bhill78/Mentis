<#
Back to Python alone on the public port: no front. docs/rust/R1-acceptance.md, "Rollback".

    powershell -File docs\cutover\rollback-to-python.ps1 [-RunDir <dir>] [-Launcher <mentis-launch.exe>]

-RunDir is the launcher's, by default %LOCALAPPDATA%\Mentis\run\8760. -Launcher is by default
mentis-launch.exe beside the running front.

THIS ENDS LIVE RUNS, as any Python restart does, so it always asks: answered no, or with nobody to
answer, it changes nothing and exits 3. Rust wrote nothing to the Brain, so there is nothing of
Rust's to undo, and Python's startup acts are its own.

Nothing watches or retries it. The launcher's state goes, because no front or private port is left
for it to describe.
#>
param(
  [string]$RunDir = '',
  [string]$Launcher = ''
)
$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
. (Join-Path $scriptDir 'launch-common.ps1')

if (-not $RunDir) { $RunDir = Join-Path $env:LOCALAPPDATA 'Mentis\run\8760' }
$state = Read-LaunchFile $RunDir 'launch.json'
$args_ = Read-LaunchFile $RunDir 'launch-args.json'
if (-not $Launcher) { $Launcher = Join-Path (Split-Path -Parent $state.front.executable) 'mentis-launch.exe' }
if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) { Refuse "no such launcher: $Launcher" }
$address = Get-ServerAddress $state

$listed = Get-ActiveRuns $address
if ($listed.Readable) {
  Write-Output "Active runs on ${address}: $($listed.Open)"
  $listed.Lines | ForEach-Object { Write-Output $_ }
} else {
  Write-Output "Active runs could not be read: $($listed.Why)"
}
if (-not (Read-Yes 'Go back to Python alone? This restarts Python and ends live runs. Yes or no:')) {
  Write-Output 'Nothing was changed.'
  exit 3
}

function Wait-PortFree([int]$Port, [int]$LimitSeconds) {
  $deadline = (Get-Date).AddSeconds($LimitSeconds)
  while ((Get-Date) -lt $deadline) {
    if (-not (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)) { return $true }
    Start-Sleep -Milliseconds 200
  }
  return $false
}

# The front first, so nothing is answered 503 for longer than it has to be. One already dead has
# nothing to stop, and the port says which.
& $Launcher stop --run-dir $RunDir --front 2>&1 | ForEach-Object { Write-Output "$_" }
if (-not (Wait-PortFree $state.public_port 5)) { Refuse "the front didn't leave port $($state.public_port); Python hasn't been touched" }

# Python's tree, as today. Only the process the launcher recorded, and only if it still is that.
$python = Get-CimInstance Win32_Process -Filter "ProcessId=$($state.python.pid)" -ErrorAction SilentlyContinue
if ($python -and $python.ExecutablePath -and ([IO.Path]::GetFullPath($python.ExecutablePath) -ieq [IO.Path]::GetFullPath($state.python.executable))) {
  & "$env:SystemRoot\System32\taskkill.exe" /T /F /PID $state.python.pid | Out-Null
}
if (-not (Wait-PortFree $state.private_port 30)) { Refuse "THE FRONT IS DOWN and something still holds private port $($state.private_port)" }

$arguments = @('-m', 'mentis.web', $state.brain, '--host', $state.public_host, '--port', "$($state.public_port)", '--workspace', $args_.workspace)
foreach ($root in @($args_.writable_roots)) { if ($root) { $arguments += @('--writable-root', $root) } }
# --mars's value holds quotes a command line would have to escape, so it goes as DAY-TO-DAY's does.
$set = @{ MENTIS_FLUID_DIST = $args_.dist }
if ($args_.mars) { $set['MENTIS_MARS_COMMAND'] = $args_.mars }
$log = Join-Path $RunDir 'python.log'
$started = Start-Outside 'python-alone' $args_.python $arguments $args_.code $RunDir $log $set

$deadline = (Get-Date).AddSeconds(240)
while ($true) {
  try {
    $answer = Invoke-WebRequest -UseBasicParsing -Uri "$address/api/server" -TimeoutSec 5
    if ($answer.StatusCode -eq 200) { break }
  } catch { }
  if (Test-Path -LiteralPath $started.ExitFile) { Refuse "Python exited without answering:`n$(Get-LogTail $log)" }
  if ((Get-Date) -gt $deadline) { Refuse "Python did not answer on $address within 240 s:`n$(Get-LogTail $log)" }
  Start-Sleep -Milliseconds 200
}

Remove-Item -LiteralPath (Join-Path $RunDir 'launch.json') -Force
Write-Output "Python alone on $address, no front. Live runs ended, and the launcher's state is gone."
exit 0
