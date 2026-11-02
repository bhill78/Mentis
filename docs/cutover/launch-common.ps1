<#
What deploy-front.ps1 and rollback-to-python.ps1 share. Dot-sourced, never run.
docs/rust/contracts/launcher.md says what each may do. Nothing here watches or retries.
#>

function Refuse([string]$Words) {
  [Console]::Error.WriteLine("refused: $Words")
  exit 3
}

function Read-LaunchFile([string]$RunDir, [string]$Name) {
  $path = Join-Path $RunDir $Name
  if (-not (Test-Path -LiteralPath $path)) { Refuse "$path does not exist: nothing was started by the launcher there" }
  $read = Get-Content -LiteralPath $path -Raw -Encoding UTF8 | ConvertFrom-Json
  if ($read.format -ne 1) { Refuse "$path says format $($read.format), and this script reads 1" }
  return $read
}

function Get-ServerAddress($State) {
  $hostName = $State.public_host
  if ($hostName -in @('0.0.0.0', '::', '[::]')) { $hostName = '127.0.0.1' }
  return "http://${hostName}:$($State.public_port)"
}

function Get-OwnerJson([string]$Url) {
  return Invoke-RestMethod -Uri $Url -Headers @{ 'X-Mentis-Client' = '1' } -TimeoutSec 15
}

# THE RECORD'S OPEN RUNS, with what the server says of each. `/fluid/api/runs` answers only for ids
# it is given, so `/fluid/api/home/activity` names them first. An open run this Python doesn't hold
# reads "state unknown": it counts as active, because asking too often costs a question and not
# asking can cost a run. Could not read is said as that, never as nothing running.
function Get-ActiveRuns([string]$Address) {
  try {
    $activity = Get-OwnerJson "$Address/fluid/api/home/activity?limit=64"
    $open = [int]$activity.open
    $ids = @($activity.items | Select-Object -First $open)
    $lines = @()
    if ($ids.Count -gt 0) {
      $runs = Get-OwnerJson "$Address/fluid/api/runs?ids=$($ids -join ',')"
      if ($runs.runtime_why_not) { throw "what this server holds could not be asked: $($runs.runtime_why_not)" }
      foreach ($run in @($runs.runs)) {
        $lines += "  $($run.id) $($run.participant_name) $($run.runtime): $($run.state), $($run.words)"
      }
    }
    if ($open -gt $ids.Count) { $lines += "  and $($open - $ids.Count) more" }
    return @{ Readable = $true; Open = $open; Ids = $ids; Lines = $lines; Why = $null }
  } catch {
    return @{ Readable = $false; Open = 0; Ids = @(); Lines = @(); Why = $_.Exception.Message }
  }
}

# A person's answer, from standard input. Nobody there is no. So a script nobody can answer changes
# nothing. The question isn't Write-Output: that would be part of what this returns, and always true.
function Read-Yes([string]$Question) {
  [Console]::Out.WriteLine($Question)
  try { $answer = [Console]::In.ReadLine() } catch { $answer = $null }
  return ($null -ne $answer -and $answer.Trim() -match '^(?i:y|yes)$')
}

function Get-Digest([string]$Path) {
  if ($Path -and (Test-Path -LiteralPath $Path)) { return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant() }
  return 'unknown, the file is gone'
}

function ConvertTo-CmdWord([string]$Word) {
  return '"' + $Word.Replace('%', '%%') + '"'
}

# Started through Win32_Process.Create, as mars-switch does, to leave any job the caller is in.
# That process has the user's environment and not this session's, so what this session sets for
# Mentis goes in a .cmd beside it, as DAY-TO-DAY's own launcher does. Never the boot secret: the
# launcher gives that to what it starts, from launch.json.
function Start-Outside([string]$Name, [string]$Exe, [string[]]$Arguments, [string]$WorkingDirectory, [string]$RunDir, [string]$Log, [hashtable]$Set = @{}) {
  $cmdFile = Join-Path $RunDir "$Name.cmd"
  $exitFile = Join-Path $RunDir "$Name.exit"
  Remove-Item -LiteralPath $exitFile -Force -ErrorAction SilentlyContinue
  $lines = @('@echo off', 'chcp 65001 >nul')
  foreach ($variable in Get-ChildItem env:) {
    if ($variable.Name -match '^(MENTIS|MARS|PYTHON)' -and $variable.Name -ne 'MENTIS_BOOT_SECRET') {
      $lines += "set `"$($variable.Name)=$($variable.Value.Replace('%', '%%'))`""
    }
  }
  foreach ($key in $Set.Keys) { $lines += "set `"$key=$($Set[$key].Replace('%', '%%'))`"" }
  $words = @($Exe) + $Arguments | ForEach-Object { ConvertTo-CmdWord $_ }
  $lines += "$($words -join ' ') 1>>$(ConvertTo-CmdWord $Log) 2>&1"
  $lines += "if errorlevel 1 (echo 3 >$(ConvertTo-CmdWord $exitFile)) else (echo 0 >$(ConvertTo-CmdWord $exitFile))"
  [IO.File]::WriteAllText($cmdFile, (($lines -join "`r`n") + "`r`n"), (New-Object Text.UTF8Encoding($false)))
  $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
  $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
    CommandLine               = "cmd.exe /d /c `"$cmdFile`""
    CurrentDirectory          = $WorkingDirectory
    ProcessStartupInformation = $startup
  }
  if ($created.ReturnValue -ne 0) { Refuse "Win32_Process.Create returned $($created.ReturnValue) for $Exe" }
  return @{ Pid = [int]$created.ProcessId; ExitFile = $exitFile; Log = $Log }
}

function Wait-LauncherExit($Started, [int]$LimitSeconds) {
  $deadline = (Get-Date).AddSeconds($LimitSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-Path -LiteralPath $Started.ExitFile) {
      return [int]((Get-Content -LiteralPath $Started.ExitFile -Raw).Trim())
    }
    Start-Sleep -Milliseconds 200
  }
  return $null
}

function Get-LogTail([string]$Log) {
  if (Test-Path -LiteralPath $Log) { return ((Get-Content -LiteralPath $Log -Tail 20) -join "`n") }
  return ''
}
