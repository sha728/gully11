# Copy your local Gully11 database (players, stats, venues, legends) to a hosted
# Postgres, e.g. Neon:
#   .\api\scripts\copy_db.ps1 -Target "postgresql://user:pass@host/db?sslmode=require"
# Runs pg_dump/psql inside the local Postgres container, so nothing else needs
# installing. The app's own tables (drafts, challenges, auctions, seasons) are
# copied empty: the dev site starts without your local test games.
param([Parameter(Mandatory = $true)][string]$Target)

$container = "gully11-postgres-1"
$userData = @("xi_drafts", "xi_challenges", "sim_results", "auction_rooms", "seasons")
$exclude = $userData | ForEach-Object { "--exclude-table-data=$_" }

Write-Host "Dumping the local database..."
docker exec $container pg_dump -U gully11 -d gully11 --no-owner --no-privileges --clean --if-exists @exclude -f /tmp/gully11.sql
if ($LASTEXITCODE -ne 0) { throw "pg_dump failed" }

Write-Host "Loading it into the target (this replaces those tables there)..."
docker exec $container psql "$Target" -v ON_ERROR_STOP=1 -q -f /tmp/gully11.sql
if ($LASTEXITCODE -ne 0) { throw "loading into the target failed" }
docker exec $container rm /tmp/gully11.sql

Write-Host "Done. Player rows on the target:"
docker exec $container psql "$Target" -At -c "SELECT count(*) FROM players"
