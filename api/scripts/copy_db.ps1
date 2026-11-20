# Copy your local Gully11 player data (players, stats, venues, legends) to a hosted
# Postgres, e.g. Neon:
#   .\api\scripts\copy_db.ps1                  # asks for the connection string (hidden)
#   .\api\scripts\copy_db.ps1 -Target "postgresql://user:pass@host/db?sslmode=require"
# Runs pg_dump/psql inside the local Postgres container, so nothing else needs
# installing.
#
# By default only the player-data tables are replaced; the app's own tables (drafts,
# challenges, auctions, seasons, the daily leaderboard) on the target are left alone,
# so refreshing the data never wipes what people have played. -Fresh copies the whole
# database instead (app tables empty), for setting up a new target.
param([string]$Target, [switch]$Fresh)

# No -Target: ask for it (input hidden, never echoed), so nothing secret is typed on
# the command line or kept in the shell history.
if (-not $Target) {
    $secure = Read-Host "Paste the Neon connection string (Ctrl+V), then press Enter" -AsSecureString
    $Target = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
if ($Target -notmatch "^postgres(ql)?://") { throw "That doesn't look like a connection string (it should start with postgresql://)." }

$container = "gully11-postgres-1"
# Tables the pipeline loads (api/db/schema/players.sql); everything else belongs to the app.
$playerTables = @("players", "player_format_stats", "player_season_stats", "player_phase_stats",
                  "player_phase_form", "player_dismissals", "player_venue_stats", "player_teams",
                  "player_opening", "venues", "venue_format_stats", "legends")
if ($Fresh) {
    $appTables = docker exec $container psql -U gully11 -d gully11 -At -c "SELECT tablename FROM pg_tables WHERE schemaname = 'public'" |
        Where-Object { $_ -and ($playerTables -notcontains $_) }
    $select = $appTables | ForEach-Object { "--exclude-table-data=$_" }
    Write-Host "Dumping the whole local database (app tables empty)..."
} else {
    $select = $playerTables | ForEach-Object { "--table=$_" }
    Write-Host "Dumping the local player data ($($playerTables.Count) tables; app tables on the target are kept)..."
}
docker exec $container pg_dump -U gully11 -d gully11 --no-owner --no-privileges --clean --if-exists @select -f /tmp/gully11.sql
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }

Write-Host "Loading it into the target (this replaces those tables there)..."
docker exec $container psql "$Target" -v ON_ERROR_STOP=1 -q -1 -f /tmp/gully11.sql
if ($LASTEXITCODE -ne 0) { throw "loading into the target failed (nothing was changed: it runs as one transaction)" }
docker exec $container rm /tmp/gully11.sql

Write-Host "Done. Player rows on the target:"
docker exec $container psql "$Target" -At -c "SELECT count(*) FROM players"
