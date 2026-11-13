# Daftarkan scrape harian jam 01.00 WIB ke Windows Task Scheduler.
#
#   powershell -ExecutionPolicy Bypass -File script\register-task.ps1
#   powershell -ExecutionPolicy Bypass -File script\register-task.ps1 -At 01:00
#
# Hapus jadwal:
#   Unregister-ScheduledTask -TaskName "Kalender Jabar Scrape" -Confirm:$false

[CmdletBinding()]
param(
    [string]$TaskName = 'Kalender Jabar Scrape',
    [string]$At = '01:00',
    [string]$RepoPath = ''
)

$ErrorActionPreference = 'Stop'

if (-not $RepoPath) {
    $RepoPath = Split-Path -Parent $PSScriptRoot
}

$repo = (Resolve-Path $RepoPath).Path
$runner = Join-Path $repo 'script\run-daily.ps1'
if (-not (Test-Path $runner)) {
    throw "Tidak ditemukan: $runner"
}

$waktu = [datetime]::ParseExact($At, 'HH:mm', $null)

$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument ('-NoProfile -ExecutionPolicy Bypass -File "{0}" -RepoPath "{1}"' -f $runner, $repo) `
    -WorkingDirectory $repo

$trigger = New-ScheduledTaskTrigger -Daily -At $waktu

# StartWhenAvailable: kalau PC mati saat jadwal, jalankan begitu PC hidup.
# WakeToRun sengaja tidak dipakai agar tidak butuh hak administrator.
$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30) `
    -MultipleInstances IgnoreNew

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Principal $principal `
    -Description 'Scrape harian kalender pendidikan Disdik Jabar lalu push ke GitHub' `
    -Force | Out-Null

$info = Get-ScheduledTask -TaskName $TaskName
Write-Host "Task terdaftar : $($info.TaskName)"
Write-Host "Status         : $($info.State)"
Write-Host "Jadwal         : setiap hari $At (waktu lokal)"
Write-Host "Repo           : $repo"
Write-Host "Log            : $repo\logs\scrape-YYYY-MM.log"
Write-Host ""
Write-Host "Uji sekarang   : Start-ScheduledTask -TaskName '$TaskName'"
