<#
DAY-TO-DAY cutover: the new Mentis takes over a Brain. Run by the owner.

    powershell -File docs\cutover\cutover.ps1 -Brain <brain dir> [-Port 8760]
        [-Code C:\Work\Mentis-dayday] [-Workspace <dir>] [-Owner ent-5936369158a8] [-Leave]

Rehearse it first on a copy (-Brain C:\Work\Mentis-brains\<copy> -Port 8830). On the live
Brain it is run only after Mark IV's server is stopped and the Brain is backed up (see
docs/cutover/README.md). Every step goes through the tools that already exist and are
idempotent, so a step that fails is fixed and the script run again.

1. Serve the Brain with the new Mentis.
2. Ladder vocabulary repair and migration of Mark IV candidates (through the server).
3. Stop; operating vocabulary; baseline v3 with the live counterparts named.
4. Serve again; establish the owner-approved governance; decline the competing candidates.
5. Leave the server running for DAY-TO-DAY (-Leave), or stop it (rehearsal).
#>
param(
  [Parameter(Mandatory = $true)][string]$Brain,
  [int]$Port = 8760,
  [string]$Code = "C:\Work\Mentis",
  [string]$Workspace = "C:\Work\Mentis-workspace\day-to-day",
  [string]$Owner = "ent-5936369158a8",
  [string]$Mars = '"C:\Work\MARS-venv\Scripts\mars.exe" stdio',
  [string]$Log = "",
  [switch]$Leave
)
$ErrorActionPreference = "Stop"
$py = "C:\Work\Mentis\.venv\Scripts\python.exe"
$server = "http://127.0.0.1:$Port"
$env:MARS_BACKENDS_FILE = "$env:LOCALAPPDATA\mars\backends.json"
$env:PYTHONIOENCODING = "utf-8"
if (-not $Log) { $Log = Join-Path $Workspace "cutover-$(Get-Date -Format yyyyMMdd-HHmmss).log" }
New-Item -ItemType Directory -Force $Workspace | Out-Null
function Say($m) { "$(Get-Date -Format HH:mm:ss) $m" | Tee-Object -FilePath $Log -Append }
function Run($what, [string[]]$a) {
  Say "== $what"
  & $py @a 2>&1 | Tee-Object -FilePath $Log -Append
  if ($LASTEXITCODE -ne 0) { throw "$what failed (exit $LASTEXITCODE); see $Log" }
}
function Start-Mentis {
  $env:MENTIS_MARS_COMMAND = $Mars   # an argument with a space would be split by Start-Process
  $p = Start-Process -FilePath $py -ArgumentList "-m","mentis.web","`"$Brain`"","--port","$Port","--workspace","`"$Workspace`"" `
       -WorkingDirectory $Code -WindowStyle Hidden -PassThru -RedirectStandardError (Join-Path $Workspace "server.err.log")
  for ($i = 0; $i -lt 90; $i++) {
    try { $s = Invoke-RestMethod -Headers @{"X-Mentis-Client"="1"} "$server/api/server" -TimeoutSec 3; Say "serving $($s.corpus) (commit $($s.code.commit))"; return $p } catch { Start-Sleep -Seconds 2 }
  }
  throw "the server did not answer on $server"
}
function Stop-Mentis($p) { if ($p -and -not $p.HasExited) { Stop-Process -Id $p.Id -Confirm:$false; Start-Sleep -Seconds 2 } }

Push-Location $Code
try {
  if (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue) { throw "port $Port is in use: stop whatever serves it first" }
  $srv = Start-Mentis
  Run "ladder vocabulary repair and candidate migration" @("tools\ladder_vocabulary.py", "--server", $server, "--apply", "--migrate-proposed", "--attributed-to", $Owner)
  Stop-Mentis $srv
  Run "operating vocabulary" @("tools\operating_vocabulary.py", $Brain, "--attributed-to", $Owner, "--live")
  Run "baseline v3" @("-m", "mentis.bootstrap.baseline", $Brain, "--owner", "@brian",
      "--match", "repair-scope=ent-0e43bf39866b", "--match", "finish-tests=ent-58aa9a229cac",
      "--match", "name-the-runtime=ent-08b6d3e67f54", "--match", "introduced-by-this-work=ent-5717950cf451",
      "--match", "git-belongs-to-the-work=ent-6121edbe2f8c", "--match", "coordinated-work=ent-8884b34d4596")
  $srv = Start-Mentis
  Run "approved governance (dry run)" @("tools\establish_governance.py", "--server", $server)
  Run "approved governance" @("tools\establish_governance.py", "--server", $server, "--apply", "--attributed-to", $Owner)
  if (-not $Leave) { Stop-Mentis $srv; Say "done; server stopped" } else { Say "done; the new Mentis is serving $Brain on $server" }
} finally { Pop-Location }
