@echo off
REM Sealos Cloud Deploy Script
REM Please modify the config below

echo ========================================
echo   Sealos Cloud Deploy Tool
echo ========================================
echo.

REM Check Docker installed
echo [CHECK] Checking Docker installed...
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Docker not installed
    echo Please install Docker Desktop: https://www.docker.com/products/docker-desktop
    echo.
    pause
    exit /b 1
)
echo [OK] Docker installed
echo.

REM Check Docker running
echo [CHECK] Checking Docker running...
docker info >nul 2>nul
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Docker not running
    echo Please start Docker Desktop
    echo.
    pause
    exit /b 1
)
echo [OK] Docker running
echo.

REM Config
set DOCKER_USERNAME=your-dockerhub-username
set APP_NAME=pdf-qa-system
set DASHSCOPE_API_KEY=sk-your-api-key-here

REM Build image
echo [1/3] Building Docker image...
echo       Image: %DOCKER_USERNAME%/%APP_NAME%:latest
echo.
docker build -t %DOCKER_USERNAME%/%APP_NAME%:latest .
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Build failed
    echo.
    pause
    exit /b 1
)
echo [OK] Build success
echo.

REM Login
echo [2/3] Login Docker Hub...
echo       Input username and password
echo.
docker login
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Login failed
    echo.
    pause
    exit /b 1
)
echo [OK] Login success
echo.

REM Push
echo [3/3] Pushing image to Docker Hub...
docker push %DOCKER_USERNAME%/%APP_NAME%:latest
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Push failed
    echo.
    pause
    exit /b 1
)
echo [OK] Push success

echo.
echo ========================================
echo   Deploy Complete!
echo ========================================
echo.
echo Next Steps:
echo.
echo 1. Visit https://cloud.sealos.io and login
echo 2. Click App Management - App - Create App
echo 3. Config app:
echo    - Name: %APP_NAME%
echo    - Image: %DOCKER_USERNAME%/%APP_NAME%:latest
echo    - CPU: 0.5 Core
echo    - Memory: 512 MiB
echo    - Port: 8501
echo 4. Add env:
echo    - DASHSCOPE_API_KEY=%DASHSCOPE_API_KEY%
echo 5. Create domain and click Create
echo.
echo Your app URL: https://%APP_NAME%-xxx.sealos.run
echo.
echo ========================================
pause
