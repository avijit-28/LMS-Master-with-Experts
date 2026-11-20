<#
.SYNOPSIS
    Registers automated Windows Task Scheduler jobs for EduPlatform LMS backups.
.DESCRIPTION
    Configures:
    1. Daily Full Backup at 02:00 AM UTC
    2. Intraday Differential Backups at 08:00, 14:00, and 20:00 UTC
    Run once as Administrator.
#>
param(
    [string]$ScriptPath = "D:\avi\Project\MVC\LMS\scripts\backup\LmsBackup.ps1",
    [string]$DatabaseName = "LMS"
)

Write-Host "Registering EduPlatform LMS Scheduled Backup Tasks..." -ForegroundColor Cyan

# Verify script path
if (-not (Test-Path $ScriptPath)) {
    Write-Error "Script file not found at: $ScriptPath"
    exit 1
}

# 1. Daily Full Backup at 02:00 AM
$actFull = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -BackupType FULL -DatabaseName `"$DatabaseName`""
$trigFull = New-ScheduledTaskTrigger -Daily -At "02:00"
Register-ScheduledTask -TaskName "LMS_Database_Full_Backup" -Action $actFull -Trigger $trigFull -User "NT AUTHORITY\SYSTEM" -RunLevel Highest -Force
Write-Host "[x] Registered 'LMS_Database_Full_Backup' (Daily at 02:00 AM)" -ForegroundColor Green

# 2. Intraday Differential Backups at 08:00, 14:00, 20:00
$actDiff = New-ScheduledTaskAction -Execute "PowerShell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`" -BackupType DIFF -DatabaseName `"$DatabaseName`""
$trigDiff1 = New-ScheduledTaskTrigger -Daily -At "08:00"
$trigDiff2 = New-ScheduledTaskTrigger -Daily -At "14:00"
$trigDiff3 = New-ScheduledTaskTrigger -Daily -At "20:00"
Register-ScheduledTask -TaskName "LMS_Database_Diff_Backup" -Action $actDiff -Trigger @($trigDiff1, $trigDiff2, $trigDiff3) -User "NT AUTHORITY\SYSTEM" -RunLevel Highest -Force
Write-Host "[x] Registered 'LMS_Database_Diff_Backup' (Daily at 08:00, 14:00, 20:00)" -ForegroundColor Green

Write-Host "Scheduled tasks successfully registered." -ForegroundColor Green
