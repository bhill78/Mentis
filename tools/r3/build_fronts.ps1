# The fronts the barrier's tests run on, each a build of this tree: `docs/rust/R3-mirror.md`, section 8.
# The probe, and one control per way of getting the barrier wrong. None of it is a release.
#
#   tools\r3\build_fronts.ps1 <directory>
#
# Leaves <directory>\<name>\mentis-server.exe, and claim_reader.exe beside them.
param([Parameter(Mandatory)] [string] $Directory)
$ErrorActionPreference = 'Stop'
$target = if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { Join-Path (Get-Location) 'target' }
$builds = [ordered]@{
    'probe'       = 'tail-probe'
    'after-first' = 'mutant-release-after-first-write'
    'before-write' = 'mutant-release-before-write'
    'no-serve'    = 'mutant-no-serve-check'
}
foreach ($name in $builds.Keys) {
    cargo build -p mentis-server --bin mentis-server --features $builds[$name]
    if ($LASTEXITCODE) { throw "cargo build for $name exited $LASTEXITCODE" }
    $into = Join-Path $Directory $name
    New-Item -ItemType Directory -Force $into | Out-Null
    Copy-Item (Join-Path $target 'debug\mentis-server.exe') $into
}
cargo build -p mentis-server --example claim_reader
if ($LASTEXITCODE) { throw "cargo build for claim_reader exited $LASTEXITCODE" }
Copy-Item (Join-Path $target 'debug\examples\claim_reader.exe') $Directory
