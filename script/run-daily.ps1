# Jalankan scrape kalender pendidikan Jabar lalu commit + push kalau ada perubahan.
#
# Dipakai oleh Windows Task Scheduler (lihat register-task.ps1) karena API
# Disdik menolak IP datacenter (GitHub Actions kena 403 Cloudflare).
#
# Pemakaian manual:
#   powershell -ExecutionPolicy Bypass -File script\run-daily.ps1
#   powershell -ExecutionPolicy Bypass -File script\run-daily.ps1 -RepoPath "C:\path\repo"

[CmdletBinding()]
param(
    [string]$RepoPath = '',
    [string]$Branch = 'main'
)

$ErrorActionPreference = 'Stop'

if (-not $RepoPath) {
    $RepoPath = Split-Path -Parent $PSScriptRoot
}

$repo = (Resolve-Path $RepoPath).Path
$logDir = Join-Path $repo 'logs'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = Join-Path $logDir ('scrape-{0:yyyy-MM}.log' -f (Get-Date))

function Write-Log {
    param([string]$Message)
    $line = '{0}  {1}' -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Write-Host $line
    Add-Content -Path $logFile -Value $line
}

if (-not (Test-Path (Join-Path $repo 'script\scrape-kalender.py'))) {
    Write-Log "GAGAL: script/scrape-kalender.py tidak ditemukan di $repo"
    exit 1
}

Push-Location $repo
try {
    Write-Log 'Mulai scrape kalender pendidikan Jabar'

    $env:PYTHONIOENCODING = 'utf-8'
    python 'script/scrape-kalender.py' 2>&1 | ForEach-Object { Write-Log $_ }
    if ($LASTEXITCODE -ne 0) {
        throw "scraper gagal dengan exit code $LASTEXITCODE"
    }

    git add -- data
    git diff --cached --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Log 'Tidak ada perubahan data, tidak ada commit.'
        exit 0
    }

    $pesan = 'chore(data): update kalender pendidikan Jabar {0}' -f (Get-Date -Format 'yyyy-MM-dd')
    git commit -m $pesan | ForEach-Object { Write-Log $_ }
    if ($LASTEXITCODE -ne 0) { throw "git commit gagal" }

    git push origin $Branch 2>&1 | ForEach-Object { Write-Log $_ }
    if ($LASTEXITCODE -ne 0) { throw "git push gagal" }

    Write-Log 'Selesai: perubahan sudah di-push.'
}
catch {
    Write-Log "GAGAL: $($_.Exception.Message)"
    exit 1
}
finally {
    Pop-Location
}
