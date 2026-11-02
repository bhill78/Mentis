<#
Replace the Rust front beside a running Python. docs/rust/contracts/launcher.md, "Deploying".

    powershell -File docs\cutover\deploy-front.ps1 -Front <binary> [-RunDir <dir>] [-YesWhenIdle]
        [-Launcher <mentis-launch.exe>]

-RunDir is the launcher's, by default %LOCALAPPDATA%\Mentis\run\8760. -Launcher is by default
mentis-launch.exe beside -Front. -YesWhenIdle is the owner's standing yes for an accepted front-only
release, and only when no run is active: with one active, or a list that can't be read, it asks all
the same. Whether a release is accepted isn't something this can know: whoever runs it answers for
that. Exit 3 means nothing was changed, unless it says the front is down.

It never restarts Python. A release that needs that isn't front-only, and goes back to the owner.
Processes survive; a run may be affected (docs/rust-front-restart.md).
#>
param(
  [Parameter(Mandatory = $true)][string]$Front,
  [string]$RunDir = '',
  [switch]$YesWhenIdle,
  [string]$Launcher = ''
)
$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
if (-not $scriptDir) { $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path }
. (Join-Path $scriptDir 'launch-common.ps1')

if (-not $RunDir) { $RunDir = Join-Path $env:LOCALAPPDATA 'Mentis\run\8760' }
if (-not (Test-Path -LiteralPath $Front -PathType Leaf)) { Refuse "no such front binary: $Front" }
$Front = (Resolve-Path -LiteralPath $Front).Path
if (-not $Launcher) { $Launcher = Join-Path (Split-Path -Parent $Front) 'mentis-launch.exe' }
if (-not (Test-Path -LiteralPath $Launcher -PathType Leaf)) { Refuse "no such launcher: $Launcher" }
$Launcher = (Resolve-Path -LiteralPath $Launcher).Path

$state = Read-LaunchFile $RunDir 'launch.json'
$address = Get-ServerAddress $state
$oldDigest = Get-Digest $state.front.executable
$newDigest = Get-Digest $Front

# Steps 1 to 4. A run nobody has been asked about stops it, however late it appears.
$answeredFor = @{}
$idleSaidYes = $false
while ($true) {
  $listed = Get-ActiveRuns $address
  $ask = $null
  if (-not $listed.Readable) {
    $ask = "Active runs could not be read: $($listed.Why)"
  } else {
    $unasked = @($listed.Ids | Where-Object { -not $answeredFor.ContainsKey($_) })
    if ($unasked.Count -gt 0 -or ($listed.Open -gt $answeredFor.Count)) {
      $ask = "Active runs on ${address}: $($listed.Open)"
      $listed.Lines | ForEach-Object { Write-Output $_ }
    } elseif ($listed.Open -eq 0 -and -not $idleSaidYes) {
      if ($YesWhenIdle) { $idleSaidYes = $true; Write-Output "No active runs on $address."; break }
      $ask = "No active runs on $address."
    } else { break }
  }
  Write-Output $ask
  if (-not (Read-Yes 'Replace the front? A call in the gap fails, and a run may change course. Yes or no:')) {
    Write-Output 'Nothing was changed.'
    exit 3
  }
  if (-not $listed.Readable) { break }
  $listed.Ids | ForEach-Object { $answeredFor[$_] = $true }
  if ($listed.Open -eq 0) { $idleSaidYes = $true }
}

# Step 5.
$clock = [Diagnostics.Stopwatch]::StartNew()
$stopping = & $Launcher stop --run-dir $RunDir --front 2>&1
if ($LASTEXITCODE -ne 0) {
  [Console]::Error.WriteLine(($stopping | Out-String).Trim())
  exit 3
}
$launcherLog = Join-Path $RunDir 'launcher.log'
$started = Start-Outside 'deploy-front' $Launcher @('--only', 'front', '--run-dir', $RunDir, '--front', $Front) $RunDir $RunDir $launcherLog
$exit = Wait-LauncherExit $started 60
if ($exit -ne 0) {
  [Console]::Error.WriteLine("THE FRONT IS DOWN: the old one stopped, and the new one did not start (exit $exit). Python is still running.")
  [Console]::Error.WriteLine((Get-LogTail $launcherLog))
  [Console]::Error.WriteLine("The previous binary: $($state.front.executable). To start it: `"$Launcher`" --only front --run-dir `"$RunDir`" --front `"$($state.front.executable)`"")
  exit 3
}
$clock.Stop()

# Step 6, a line for the owner's report.
$after = Read-LaunchFile $RunDir 'launch.json'
$gap = $clock.Elapsed.TotalSeconds.ToString('0.0', [Globalization.CultureInfo]::InvariantCulture)
Write-Output "Front replaced on ${address}: old sha256 $oldDigest, new sha256 $newDigest, gap $gap s, front pid $($state.front.pid) to $($after.front.pid), Python pid $($after.python.pid) unchanged."
exit 0
