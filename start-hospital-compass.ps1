$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiPath = Join-Path $projectRoot 'apps\api'
$webPath = Join-Path $projectRoot 'apps\web'
$hospitalDatabasePath = 'F:\hospital-database\db\hospital_database.db'

if (-not (Test-Path -LiteralPath $hospitalDatabasePath -PathType Leaf)) {
  throw "Hospital database was not found: $hospitalDatabasePath"
}

Start-Process powershell.exe -ArgumentList @(
  '-NoExit', '-Command',
  "`$env:ANYSEARCH_API_KEY=[Environment]::GetEnvironmentVariable('ANYSEARCH_API_KEY','User'); `$env:BOCHA_API_KEY=[Environment]::GetEnvironmentVariable('BOCHA_API_KEY','User'); `$env:DEEPSEEK_API_KEY=[Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User'); `$env:FEEDBACK_ADMIN_TOKEN=[Environment]::GetEnvironmentVariable('FEEDBACK_ADMIN_TOKEN','User'); `$env:FEEDBACK_DATABASE_PATH=[Environment]::GetEnvironmentVariable('FEEDBACK_DATABASE_PATH','User'); `$env:DEEPSEEK_MODEL='deepseek-chat'; `$env:HOSPITAL_COMPASS_DATABASE_PATH='$hospitalDatabasePath'; `$env:HOSPITAL_COMPASS_TERTIARY_DATABASE_PATH='$hospitalDatabasePath'; Set-Location '$apiPath'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8001"
) -WindowStyle Hidden
Start-Process powershell.exe -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$webPath'; npm.cmd run dev"
) -WindowStyle Hidden
Write-Host 'Hospital Compass frontend and backend are starting.'
