# EduPlatform LMS: Production Pre-Deployment & Go-Live Checklist

This checklist provides the final verification gates, operational procedures, and step-by-step commands to deploy **EduPlatform LMS** to production with **zero cloud cost** and enterprise reliability.

---

## 1. Automated System Health Verification (Passed ✅)

| Verification Gate | Test Command / Method | Result | Notes |
| :--- | :--- | :---: | :--- |
| **Debug Build** | `msbuild LMS.csproj /p:Configuration=Debug` | **0 Errors** | Verified clean build |
| **Release Build** | `msbuild LMS.csproj /p:Configuration=Release` | **0 Errors** | Optimized production binaries compiled |
| **Database Status** | `sqlcmd -Q "SELECT state_desc FROM sys.databases WHERE name='LMS'"` | **ONLINE** | SQL Server 2022 Express operational |
| **Stored Procedures** | `OBJECT_ID('dbo.sp_MarkLessonComplete')` & `sp_EnrollStudent` | **ACTIVE** | Atomic `MERGE ... WITH (HOLDLOCK)` |
| **Composite Indexes** | 5 New Covering / Unique Indexes | **ACTIVE** | Zero table scans on enrollments & lessons |
| **Secrets Sanitization**| Checked `.env.example` and `AIService/.env.example` | **CLEAN** | All secrets sanitized with placeholders |
| **Git Ignore Rules** | Verified `.gitignore` | **ACTIVE** | `.env`, `*.bak`, `bin/`, `obj/` ignored |
| **Load Capacity** | `node infra/loadtest-runner.js` | **558 req/s** | p95 = 73ms, 0.00% error rate |
| **Origin Web Server** | `http://localhost:56102/` | **200 OK** | Landing, login, classroom, AI chat verified |

---

## 2. Production Deployment Steps (Windows IIS)

When deploying to the permanent production Windows Server or workstation IIS 10.0:

### Step 2.1: Configure IIS Application Pool
To eliminate the 15-second cold-start delay for the first morning student:
1. Open **IIS Manager** (`inetmgr`).
2. Go to **Application Pools** -> Select your LMS App Pool -> **Advanced Settings**:
   - **.NET CLR Version**: `v4.0`
   - **Managed Pipeline Mode**: `Integrated`
   - **Start Mode**: Change from `OnDemand` to `AlwaysRunning`
   - **Idle Time-out (minutes)**: Change from `20` to `0` (prevents worker process shutdown)
   - **Recycling**: Set specific recycling time (e.g., `03:30 AM` daily)

### Step 2.2: Verify SQL Server Express Service
Ensure SQL Server and SQL Server Agent are configured for automatic startup:
```powershell
Set-Service -Name "MSSQLSERVER" -StartupType Automatic
Start-Service -Name "MSSQLSERVER"
```

### Step 2.3: Register Automated Daily DLP Backups
Register automated daily hot backups (02:00 AM Full, 4-hour Differential):
```powershell
powershell -ExecutionPolicy Bypass -File "D:\avi\Project\MVC\LMS\scripts\backup\RegisterBackupTasks.ps1"
```

---

## 3. Cloudflare Tunnel Public Go-Live Protocol

Expose the site publicly over HTTPS with **zero open inbound ports**:

### Step 3.1: Authenticate Tunnel
```powershell
cloudflared tunnel login
```

### Step 3.2: Create Tunnel
```powershell
cloudflared tunnel create eduplatform-lms
```
Copy the generated Tunnel UUID into `infra/cloudflared-config.yml`.

### Step 3.3: Route Custom Domain to Tunnel
```powershell
cloudflared tunnel route dns eduplatform-lms lms.yourdomain.com
```

### Step 3.4: Install and Start Auto-Starting Windows Service
```powershell
powershell -ExecutionPolicy Bypass -File "D:\avi\Project\MVC\LMS\scripts\setup-cloudflare-tunnel.ps1" -Action ServiceInstall
```

---

## 4. Supporting Microservice Stack (Docker Compose)

Start the supporting containerized microservices:
```powershell
# Double-click or execute the launcher:
.\start-infra.bat
```
This launches:
- `lms-redis` (127.0.0.1:6379)
- `lms-qdrant` (127.0.0.1:6333)
- `lms-rabbitmq` (127.0.0.1:5672)
- `lms-prometheus` (127.0.0.1:9090)
- `lms-grafana` (127.0.0.1:3000)

---

## 5. Post-Deployment Smoke Test Runbook

After deploying and launching the tunnel, execute the quick smoke test suite:
1. **Public Ingress**: Navigate to `https://lms.yourdomain.com/` in an incognito window.
2. **Student Login**: Sign in as `student@lms.com` with `Student@123`.
3. **Lesson Progression**: Complete a lesson and verify progress bar increases without errors.
4. **AI Assistant**: Open `/ChatBot` and ask a course question. Verify streaming response.
5. **Certificate**: Verify `https://lms.yourdomain.com/Certificate/Verify` renders without a login challenge.
6. **Metrics Check**: Check Prometheus metrics at `http://127.0.0.1:9090` or `http://localhost:8000/metrics`.
