$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$apiPath = Join-Path $projectRoot 'apps\api'
$webPath = Join-Path $projectRoot 'apps\web'
$bochaKey = [Environment]::GetEnvironmentVariable('BOCHA_API_KEY', 'User')
if (-not $bochaKey) {
  Write-Error 'BOCHA_API_KEY is not configured for the current Windows user.'
  exit 1
}

Start-Process powershell.exe -ArgumentList @(
  '-NoExit', '-Command',
  "`$env:BOCHA_API_KEY=[Environment]::GetEnvironmentVariable('BOCHA_API_KEY','User'); `$env:DEEPSEEK_API_KEY=[Environment]::GetEnvironmentVariable('DEEPSEEK_API_KEY','User'); Set-Location '$apiPath'; python -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
) -WindowStyle Hidden
Start-Process powershell.exe -ArgumentList @(
  '-NoExit', '-Command',
  "Set-Location '$webPath'; npm.cmd run dev"
) -WindowStyle Hidden
Write-Host 'Hospital Compass frontend and backend are starting.'
