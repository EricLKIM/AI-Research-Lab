<#
Build a self-contained Windows release folder for Inno Setup.

Prerequisite: uv must be installed and `uv sync` must have completed.
Run from PowerShell:
  .\build_release.ps1
Then compile setup.iss with Inno Setup.
#>

[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$StageRoot = Join-Path $ProjectRoot "build\pyinstaller"
$WorkRoot = Join-Path $ProjectRoot "build\pyinstaller-work"
$SpecRoot = Join-Path $ProjectRoot "build\pyinstaller-spec"
$ReleaseRoot = Join-Path $ProjectRoot "dist\AI Research Lab"

$Uv = Get-Command uv -ErrorAction SilentlyContinue
if ($null -eq $Uv) {
    throw "uv was not found. Install uv first, then run uv sync from the project root."
}

# uv supplies PyInstaller for this build without adding it to the application
# dependencies or requiring pip to exist inside .venv.
& $Uv.Source run --with pyinstaller python -m PyInstaller --version
if ($LASTEXITCODE -ne 0) {
    throw "uv could not prepare PyInstaller for this build. Run 'uv sync' and try again."
}

if (Test-Path -LiteralPath $ReleaseRoot) {
    throw "Release folder already exists: $ReleaseRoot`nRemove or rename it before rebuilding."
}

function Invoke-PipelineBuild {
    param(
        [Parameter(Mandatory)] [string] $Name,
        [Parameter(Mandatory)] [string] $Script,
        [switch] $Windowed,
        [switch] $UseIcon
    )

    $Arguments = @(
        "--noconfirm", "--clean", "--onedir",
        "--name", $Name,
        "--distpath", $StageRoot,
        "--workpath", $WorkRoot,
        "--specpath", $SpecRoot,
        "--paths", (Join-Path $ProjectRoot "src"),
        "--collect-data", "tzdata",
        "--collect-all", "tavily_agent_toolkit"
    )
    if ($Windowed) { $Arguments += "--windowed" }
    if ($UseIcon) { $Arguments += @("--icon", (Join-Path $ProjectRoot "topic.ico")) }
    $Arguments += (Join-Path $ProjectRoot $Script)

    Write-Host "Building $Name..."
    # Run the module through Python. Calling the PyInstaller console command
    # directly can make uv's temporary trampoline look like sys.executable,
    # which prevents Windows resource updates during the final executable build.
    & $Uv.Source run --with pyinstaller python -m PyInstaller @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed while building $Name."
    }
}

Invoke-PipelineBuild -Name "AI Research Lab" -Script "scripts\app.py" -Windowed -UseIcon
Invoke-PipelineBuild -Name "Topic Research" -Script "scripts\topic_digest.py"
Invoke-PipelineBuild -Name "GDELT Dump Backfill" -Script "scripts\backfill_gdelt_dump.py"
Invoke-PipelineBuild -Name "DOC API Backfill" -Script "scripts\backfill_topic.py"
Invoke-PipelineBuild -Name "Trend Analysis" -Script "scripts\analysis.py"
Invoke-PipelineBuild -Name "Scheduled Collection" -Script "scripts\scheduled_collect.py"

New-Item -ItemType Directory -Path $ReleaseRoot | Out-Null
Copy-Item -Path (Join-Path $StageRoot "AI Research Lab\*") -Destination $ReleaseRoot -Recurse

$PipelineRoot = Join-Path $ReleaseRoot "pipelines"
New-Item -ItemType Directory -Path $PipelineRoot | Out-Null
$PipelineFolders = @{
    "Topic Research" = "topic_digest"
    "GDELT Dump Backfill" = "backfill_gdelt_dump"
    "DOC API Backfill" = "backfill_topic"
    "Trend Analysis" = "analysis"
    "Scheduled Collection" = "scheduled_collect"
}
foreach ($BuildName in $PipelineFolders.Keys) {
    $Destination = Join-Path $PipelineRoot $PipelineFolders[$BuildName]
    Copy-Item -LiteralPath (Join-Path $StageRoot $BuildName) -Destination $Destination -Recurse
}

New-Item -ItemType Directory -Path (Join-Path $ReleaseRoot "scripts") | Out-Null
Copy-Item -LiteralPath (Join-Path $ProjectRoot "scripts\register_auto_collection.ps1") -Destination (Join-Path $ReleaseRoot "scripts\register_auto_collection.ps1")
Copy-Item -LiteralPath (Join-Path $ProjectRoot "topic.ico") -Destination (Join-Path $ReleaseRoot "topic.ico")

Write-Host ""
Write-Host "Release folder created: $ReleaseRoot"
Write-Host "Next: compile setup.iss with Inno Setup."
