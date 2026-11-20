@echo off
REM ==============================================================================
REM EduPlatform LMS - Infrastructure Launcher (Redis, Qdrant, RabbitMQ, Prometheus, Grafana)
REM ==============================================================================
echo [LMS Infrastructure] Checking Docker Engine availability...

where docker >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Docker is not detected on PATH.
    echo.
    echo To enable the full Linux microservice stack on Windows at Rs. 0 cost:
    echo 1. Open an Administrator PowerShell and run: wsl --install
    echo 2. Download and install Docker Desktop for Windows: https://www.docker.com/products/docker-desktop/
    echo 3. In Docker Desktop Settings: Enable 'Use the WSL 2 based engine'.
    echo.
    echo Note: The ASP.NET MVC 5 application and standalone AIService will continue running
    echo directly on your Windows host in local fallback mode.
    pause
    exit /b 1
)

echo [LMS Infrastructure] Starting supporting containers (Redis, Qdrant, RabbitMQ, Prometheus, Grafana)...
docker compose up -d

echo.
echo [LMS Infrastructure] Checking container statuses:
docker compose ps

echo.
echo ==============================================================================
echo Infrastructure Stack Launched:
echo - Redis Cache:         127.0.0.1:6379
echo - Qdrant Vector DB:    http://127.0.0.1:6333
echo - RabbitMQ Management: http://127.0.0.1:15672 (User: lms_admin)
echo - Prometheus Metrics:  http://127.0.0.1:9090
echo - Grafana Dashboards:  http://127.0.0.1:3000 (User: admin)
echo ==============================================================================
