param([string[]]$Times = @("09:00"))

$root = Split-Path -Parent $PSScriptRoot
if (Test-Path -LiteralPath (Join-Path $root "AI Research Lab.exe")) {
    $runner = Join-Path $root "pipelines\scheduled_collect\Scheduled Collection.exe"
    $action = New-ScheduledTaskAction -Execute $runner -WorkingDirectory $root
} else {
    $python = Join-Path $root ".venv\Scripts\python.exe"
    $action = New-ScheduledTaskAction -Execute $python -Argument "-u scripts\scheduled_collect.py" -WorkingDirectory $root
}
$triggers = $Times | ForEach-Object { New-ScheduledTaskTrigger -Daily -At $_ }
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "AI Research Lab Auto Collect" -Action $action -Trigger $triggers -Settings $settings -Description "AI Research Lab scheduled collection" -Force
