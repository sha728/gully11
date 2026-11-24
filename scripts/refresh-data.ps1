# Refresh the local Gully XI player data from Cricsheet.
#
#   .\scripts\refresh-data.ps1            # run it now
#   .\scripts\refresh-data.ps1 -Register  # also run it every Monday at 06:00 (Windows Task Scheduler)
#   .\scripts\refresh-data.ps1 -Unregister
#
# Steps (each must succeed before the next; a failure stops the run, so a half-done
# refresh never reaches the database):
#   download -> parse -> names (Wikidata) -> build -> styles (Wikipedia) -> build -> load
# Names and styles cover players new since the last refresh; build runs again after
# styles because the build reads them.
#
# Only your local database changes. To put the new data on the live site, run
#   .\api\scripts\copy_db.ps1
# yourself afterwards (it asks for the Neon connection string).
#
# Needs Docker Desktop running (local Postgres) and WIKIMEDIA_CONTACT in .env.
# Each run writes a log to pipeline\data\refresh-logs\.
param([switch]$Register, [switch]$Unregister)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$taskName = "Gully XI data refresh"

if ($Unregister) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    Write-Output "Removed the scheduled task '$taskName'."
    return
}
if ($Register) {
    $action = New-ScheduledTaskAction -Execute "powershell.exe" `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -WorkingDirectory $repo
    $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 6am
    # Run as soon as possible after a missed start (PC off at 06:00), only on mains power is not required.
    $settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings `
        -Description "Refreshes the local Gully XI database from Cricsheet (scripts\refresh-data.ps1). Does not touch the live site." -Force | Out-Null
    Write-Output "Scheduled '$taskName': every Monday at 06:00, or as soon as the PC is on after that."
    return
}

$logDir = Join-Path $repo "pipeline\data\refresh-logs"
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ("refresh-{0:yyyy-MM-dd_HHmm}.log" -f (Get-Date))

function Write-Log([string]$msg) {
    $line = "{0:HH:mm:ss}  {1}" -f (Get-Date), $msg
    Write-Output $line
    Add-Content -Path $log -Value $line -Encoding utf8
}

function Invoke-Step([string]$name, [string[]]$pipelineArgs) {
    Write-Log "== $name"
    $t0 = Get-Date
    Push-Location (Join-Path $repo "pipeline")
    try {
        # uv writes progress to stderr; keep it in the log without treating it as a failure.
        $ErrorActionPreference = "Continue"
        & uv run gully-pipeline @pipelineArgs 2>&1 | ForEach-Object { Add-Content -Path $log -Value "    $_" -Encoding utf8 }
        $code = $LASTEXITCODE
    } finally {
        Pop-Location
    }
    if ($code -ne 0) {
        Write-Log "FAILED: $name (exit $code). Nothing after this step ran; see $log"
        exit 1
    }
    Write-Log ("   done in {0:N0}s" -f ((Get-Date) - $t0).TotalSeconds)
}

Write-Log "Gully XI data refresh (log: $log)"

# Local Postgres must be up for the final load; check before spending time on the rest.
$ErrorActionPreference = "Continue"
docker info *> $null
$dockerUp = $LASTEXITCODE -eq 0
$ErrorActionPreference = "Stop"
if (-not $dockerUp) {
    Write-Log "Docker isn't running, so the local database can't be loaded. Start Docker Desktop and run this again."
    exit 1
}
# Windows PowerShell treats anything a program writes to stderr (docker prints status
# there) as an error under "Stop", so native commands run under "Continue" and are
# judged by their exit code instead.
$ErrorActionPreference = "Continue"
Push-Location $repo
docker compose up -d postgres *> $null
Pop-Location
$before = (docker exec gully11-postgres-1 psql -U gully11 -d gully11 -At -c "SELECT count(*) FROM players" 2>$null)

Invoke-Step "download (Cricsheet)" @("download", "--dataset", "all")
Invoke-Step "parse" @("parse", "--dataset", "all")
Invoke-Step "names (Wikidata)" @("names")
Invoke-Step "build" @("build", "--dataset", "all")
Invoke-Step "styles (Wikipedia)" @("styles")
Invoke-Step "build again (with styles)" @("build", "--dataset", "all")
Invoke-Step "load into local Postgres" @("load")

$after = (docker exec gully11-postgres-1 psql -U gully11 -d gully11 -At -c "SELECT count(*) FROM players" 2>$null)
Write-Log "Players in the local database: $before -> $after"
Write-Log "Done. To update the live site, run: .\api\scripts\copy_db.ps1"
