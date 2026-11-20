<#
.SYNOPSIS
    Production Automated DLP & Hot Backup Engine for EduPlatform LMS SQL Server Express.
.DESCRIPTION
    Zero-Cost automation: Executes DBCC CHECKDB pre-flight verification, performs compressed
    Full/Differential backups, verifies backup headers, prunes expired files, and syncs to Cloudflare R2.
.PARAMETER BackupType
    "FULL" or "DIFF"
.PARAMETER DatabaseName
    Target database name (Default: "LMS")
#>
param(
    [ValidateSet("FULL", "DIFF")]
    [string]$BackupType = "FULL",
    [string]$ServerInstance = "localhost",
    [string]$DatabaseName = "LMS",
    [string]$BackupFolder = "C:\LMS_Backups\Database",
    [int]$RetentionDays = 7,
    [string]$RcloneRemote = "r2-lms-backup:eduplatform-backups/database"
)

$ErrorActionPreference = "Stop"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"

# Robust Log File & Directory Initialization with Emergency Fallback
$PrimaryLogDir = $BackupFolder
$EmergencyLogDir = Join-Path $env:TEMP "LMS_Backup_Emergency"
$LogFile = $null

try {
    if (-not (Test-Path $BackupFolder)) {
        New-Item -ItemType Directory -Path $BackupFolder -Force -ErrorAction Stop | Out-Null
    }
    $LogFile = Join-Path $BackupFolder "backup_log_$Timestamp.txt"
}
catch {
    Write-Warning "Failed to access or create primary backup directory: $BackupFolder. Falling back to temporary directory."
    if (-not (Test-Path $EmergencyLogDir)) {
        New-Item -ItemType Directory -Path $EmergencyLogDir -Force | Out-Null
    }
    $LogFile = Join-Path $EmergencyLogDir "backup_emergency_log_$Timestamp.txt"
}

function Write-Log([string]$Message) {
    $Line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss UTC')] $Message"
    Write-Host $Line
    if ($LogFile) {
        try { Add-Content -Path $LogFile -Value $Line -ErrorAction SilentlyContinue } catch { }
    }
}

try {
    Write-Log "=========================================================="
    Write-Log "Starting EduPlatform LMS $BackupType Backup on [$DatabaseName]"
    Write-Log "=========================================================="

    # Safe T-SQL Identifier Escaping: Replace "]" with "]]" to prevent identifier injection
    $SafeDbIdentifier = "[" + $DatabaseName.Replace("]", "]]") + "]"

    # Step 1: Pre-flight SQL Server Service Connectivity Probe
    Write-Log "Probing SQL Server instance connectivity ($ServerInstance)..."
    $pingSql = "SET NOCOUNT ON; SELECT 1;"
    $pingOutput = sqlcmd -S $ServerInstance -E -Q $pingSql -b -h -1
    if ($LASTEXITCODE -ne 0) {
        throw "SQL Server instance '$ServerInstance' is unreachable, stopped, or rejecting logins (Exit code $LASTEXITCODE). Backup aborted."
    }
    Write-Log "SQL Server instance is active and accepting queries."

    # Step 2: Database Integrity Check (DBCC CHECKDB)
    Write-Log "Executing pre-flight DBCC CHECKDB integrity check on $SafeDbIdentifier..."
    $checkSql = "DBCC CHECKDB ($SafeDbIdentifier) WITH NO_INFOMSGS, ALL_ERRORMSGS;"
    $checkOutput = sqlcmd -S $ServerInstance -E -Q $checkSql -b
    if ($LASTEXITCODE -ne 0) {
        throw "DBCC CHECKDB reported physical or logical consistency corruption on $SafeDbIdentifier! Backup aborted to protect clean snapshots. Details: $checkOutput"
    }
    Write-Log "DBCC CHECKDB passed: 0 allocation errors, 0 consistency errors."

    # Step 3: Perform Compressed Backup with Checksums
    $BackupFileName = "$($DatabaseName)_$($BackupType)_$Timestamp.bak"
    $BackupFilePath = Join-Path $BackupFolder $BackupFileName

    if ($BackupType -eq "FULL") {
        $backupSql = @"
BACKUP DATABASE $SafeDbIdentifier
TO DISK = N'$BackupFilePath'
WITH FORMAT, INIT, COMPRESSION, CHECKSUM,
NAME = N'$DatabaseName-Full Backup $Timestamp',
STATS = 10;
"@
    } else {
        $backupSql = @"
BACKUP DATABASE $SafeDbIdentifier
TO DISK = N'$BackupFilePath'
WITH DIFFERENTIAL, COMPRESSION, CHECKSUM,
NAME = N'$DatabaseName-Differential Backup $Timestamp',
STATS = 10;
"@
    }

    Write-Log "Running SQL Server Backup command..."
    sqlcmd -S $ServerInstance -E -Q $backupSql -b
    if ($LASTEXITCODE -ne 0) {
        throw "sqlcmd backup failed with exit code $LASTEXITCODE."
    }

    $fileSizeMB = [math]::Round(((Get-Item $BackupFilePath).Length / 1MB), 2)
    Write-Log "Backup archive generated: $BackupFilePath ($fileSizeMB MB)"

    # Step 4: Verify Backup Archive Header and Checksum Integrity
    Write-Log "Verifying archive integrity via RESTORE VERIFYONLY..."
    $verifySql = "RESTORE VERIFYONLY FROM DISK = N'$BackupFilePath' WITH CHECKSUM;"
    sqlcmd -S $ServerInstance -E -Q $verifySql -b
    if ($LASTEXITCODE -ne 0) {
        throw "Backup verification failed! The generated .bak file is corrupt or unreadable."
    }
    Write-Log "RESTORE VERIFYONLY passed successfully."

    # Step 5: Prune Local Files Older Than Retention Threshold
    Write-Log "Pruning local backup files older than $RetentionDays days..."
    $CutoffDate = (Get-Date).AddDays(-$RetentionDays)
    Get-ChildItem -Path $BackupFolder -Filter "$($DatabaseName)_*.bak" -ErrorAction SilentlyContinue | Where-Object {
        $_.LastWriteTime -lt $CutoffDate
    } | ForEach-Object {
        Write-Log "Pruning expired backup archive: $($_.Name)"
        Remove-Item $_.FullName -Force -ErrorAction SilentlyContinue
    }

    # Step 6: Offsite Sync to Cloudflare R2 via rclone (Optional Free Tier)
    if (Get-Command rclone -ErrorAction SilentlyContinue) {
        Write-Log "Mirroring backup archive to Cloudflare R2 ($RcloneRemote)..."
        rclone copy $BackupFilePath $RcloneRemote --fast-list
        if ($LASTEXITCODE -eq 0) {
            Write-Log "Offsite cloud sync completed successfully."
        } else {
            Write-Log "WARNING: rclone sync exited with non-zero code $LASTEXITCODE."
        }
    } else {
        Write-Log "NOTE: rclone executable not found on PATH. Skipping cloud offsite replication."
    }

    Write-Log "=== $BackupType Backup process completed successfully! ==="
    exit 0
}
catch {
    Write-Log "CRITICAL BACKUP FAILURE: $_"
    exit 1
}
