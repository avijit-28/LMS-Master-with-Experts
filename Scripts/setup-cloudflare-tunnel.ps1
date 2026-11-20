<#
.SYNOPSIS
    Production Cloudflare Tunnel Setup & Service Registrar for EduPlatform LMS.
.DESCRIPTION
    Configures an encrypted outbound tunnel connecting local Windows IIS / IIS Express
    to Cloudflare's Global Anycast Edge without opening any inbound router/firewall ports.
    Includes automated binary installation, pre-flight origin health check, and Windows
    Service registration for continuous unattended operation.
.PARAMETER Action
    "Install", "Verify", "Start", "ServiceInstall", "ServiceUninstall"
.PARAMETER ConfigPath
    Path to cloudflared-config.yml (Default: "infra/cloudflared-config.yml")
#>
param(
    [ValidateSet("Install", "Verify", "Start", "ServiceInstall", "ServiceUninstall")]
    [string]$Action = "Verify",
    [string]$ConfigPath = "D:\avi\Project\MVC\LMS\infra\cloudflared-config.yml",
    [int]$OriginPort = 56102
)

$ErrorActionPreference = "Stop"
$CloudflaredBinDir = "C:\Program Files\cloudflared"
$CloudflaredExe = Join-Path $CloudflaredBinDir "cloudflared.exe"

function Write-Step([string]$msg) {
    Write-Host "`n[STEP] $msg" -ForegroundColor Cyan
}

function Write-Success([string]$msg) {
    Write-Host "[SUCCESS] $msg" -ForegroundColor Green
}

function Write-WarnMsg([string]$msg) {
    Write-Host "[WARN] $msg" -ForegroundColor Yellow
}

# 1. Locate or Download cloudflared.exe
function Ensure-Cloudflared {
    if (Get-Command cloudflared -ErrorAction SilentlyContinue) {
        $found = (Get-Command cloudflared).Source
        Write-Success "cloudflared is installed and available on PATH: $found"
        return $found
    }

    if (Test-Path $CloudflaredExe) {
        Write-Success "cloudflared found at $CloudflaredExe"
        return $CloudflaredExe
    }

    Write-Step "cloudflared is not installed. Downloading official release from Cloudflare..."
    if (-not (Test-Path $CloudflaredBinDir)) {
        New-Item -ItemType Directory -Path $CloudflaredBinDir -Force | Out-Null
    }

    $downloadUrl = "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe"
    Invoke-WebRequest -Uri $downloadUrl -OutFile $CloudflaredExe -UseBasicParsing
    
    # Add to system PATH permanently
    $currentPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
    if ($currentPath -notlike "*$CloudflaredBinDir*") {
        [Environment]::SetEnvironmentVariable("Path", "$currentPath;$CloudflaredBinDir", "Machine")
        Write-Success "Added $CloudflaredBinDir to system PATH."
    }

    Write-Success "cloudflared downloaded successfully to $CloudflaredExe"
    return $CloudflaredExe
}

# 2. Verify Local Origin Server Health
function Test-OriginServer {
    Write-Step "Verifying local origin IIS server responsiveness on port $OriginPort..."
    try {
        $originUrl = "http://localhost:$OriginPort/"
        $response = Invoke-WebRequest -Uri $originUrl -Method GET -TimeoutSec 5 -UseBasicParsing
        if ($response.StatusCode -eq 200) {
            Write-Success "Origin server is online and responding with HTTP 200 OK."
            return $true
        } else {
            Write-WarnMsg "Origin server responded with HTTP status $($response.StatusCode)."
            return $false
        }
    }
    catch {
        Write-WarnMsg "Could not connect to origin server on port $OriginPort ($($_.Exception.Message))."
        Write-WarnMsg "Ensure IIS or IIS Express is started before initiating tunnel ingress."
        return $false
    }
}

# 3. Validate Configuration File
function Test-ConfigFile {
    Write-Step "Validating tunnel configuration manifest at '$ConfigPath'..."
    if (-not (Test-Path $ConfigPath)) {
        throw "Tunnel configuration file not found at: $ConfigPath"
    }

    $content = Get-Content -Path $ConfigPath -Raw
    if ($content -like "*YOUR_TUNNEL_UUID_HERE*") {
        Write-WarnMsg "Notice: '$ConfigPath' still contains placeholder 'YOUR_TUNNEL_UUID_HERE'."
        Write-Host "Run the following one-time commands to bind your Cloudflare account:" -ForegroundColor White
        Write-Host "  1. cloudflared tunnel login" -ForegroundColor Yellow
        Write-Host "  2. cloudflared tunnel create eduplatform-lms" -ForegroundColor Yellow
        Write-Host "  3. Update tunnel UUID and credentials-file in $ConfigPath" -ForegroundColor Yellow
        Write-Host "  4. cloudflared tunnel route dns eduplatform-lms lms.yourdomain.com" -ForegroundColor Yellow
        return $false
    }

    Write-Success "Configuration manifest appears valid and configured."
    return $true
}

# Execution Dispatcher
switch ($Action) {
    "Install" {
        $bin = Ensure-Cloudflared
        Test-OriginServer
        Test-ConfigFile
        Write-Success "Installation and pre-flight checks complete."
    }
    "Verify" {
        $bin = if (Get-Command cloudflared -ErrorAction SilentlyContinue) { (Get-Command cloudflared).Source } else { $CloudflaredExe }
        if (Test-Path $bin) {
            Write-Success "cloudflared binary located at: $bin"
            & $bin --version
        } else {
            Write-WarnMsg "cloudflared binary is not yet downloaded. Run with -Action Install."
        }
        Test-OriginServer
        Test-ConfigFile
    }
    "Start" {
        $bin = Ensure-Cloudflared
        Test-OriginServer
        Test-ConfigFile
        Write-Step "Starting cloudflared tunnel in foreground (Press Ctrl+C to terminate)..."
        & $bin tunnel --config $ConfigPath run
    }
    "ServiceInstall" {
        $bin = Ensure-Cloudflared
        Write-Step "Registering cloudflared as auto-starting Windows Service..."
        & $bin service install
        Write-Success "Windows Service registered. Service will auto-start with Windows."
    }
    "ServiceUninstall" {
        $bin = Ensure-Cloudflared
        Write-Step "Uninstalling cloudflared Windows Service..."
        & $bin service uninstall
        Write-Success "Windows Service removed."
    }
}
