@echo off
chcp 65001 >nul
REM 一站式快速部署准备脚本 (Windows 版本)

title Sealos Cloud 一键部署准备工具

echo ========================================
echo   Sealos Cloud 一键部署准备工具
echo ========================================
echo.

REM 检查 Docker 是否安装
where docker >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] Docker 未安装
    echo 请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)
echo [成功] Docker 已安装

REM 检查 Docker 是否运行
docker info >nul 2>nul
if %errorlevel% neq 0 (
    echo [错误] Docker 未运行
    echo 请启动 Docker Desktop
    pause
    exit /b 1
)
echo [成功] Docker 正在运行

echo.
echo 请输入以下配置信息:
echo.

REM 获取 Docker Hub 用户名
set /p DOCKER_USERNAME=Docker Hub 用户名 (例如：kalvi):
if "%DOCKER_USERNAME%"=="" (
    echo 用户名不能为空
    pause
    exit /b 1
)

REM 获取应用名称
set /p APP_NAME=应用名称 (默认：pdf-qa-system):
if "%APP_NAME%"=="" set APP_NAME=pdf-qa-system

REM 获取 API Key
set /p DASHSCOPE_API_KEY=DashScope API Key (sk-开头，可选):

echo.
echo 配置信息:
echo    Docker Hub 用户名：%DOCKER_USERNAME%
echo    应用名称：%APP_NAME%
if not "%DASHSCOPE_API_KEY%"=="" (
    echo    API Key: %DASHSCOPE_API_KEY:~0,10...%DASHSCOPE_API_KEY:~-5%
) else (
    echo    API Key: (未设置)
)
echo.

set /p confirm=确认配置是否正确？(y/n):
if /i not "%confirm%"=="y" (
    echo 已取消
    pause
    exit /b 1
)

REM 更新部署脚本中的配置
if exist "deploy-sealos.bat" (
    echo [成功] 更新部署脚本配置...
    powershell -Command "(Get-Content 'deploy-sealos.bat') -replace 'DOCKER_USERNAME=.*', 'DOCKER_USERNAME=%DOCKER_USERNAME%' -replace 'APP_NAME=.*', 'APP_NAME=%APP_NAME%' -replace 'DASHSCOPE_API_KEY=.*', 'DASHSCOPE_API_KEY=%DASHSCOPE_API_KEY%' | Set-Content 'deploy-sealos.bat'"
)

echo.
echo [1/3] 开始构建 Docker 镜像...
docker build -t %DOCKER_USERNAME%/%APP_NAME%:latest .

if %errorlevel% neq 0 (
    echo [错误] 镜像构建失败
    pause
    exit /b 1
)
echo [成功] 镜像构建成功

echo.
echo [2/3] 登录 Docker Hub...
docker login

if %errorlevel% neq 0 (
    echo [错误] Docker Hub 登录失败
    pause
    exit /b 1
)

echo.
echo [3/3] 推送镜像到 Docker Hub...
docker push %DOCKER_USERNAME%/%APP_NAME%:latest

if %errorlevel% neq 0 (
    echo [错误] 镜像推送失败
    pause
    exit /b 1
)
echo [成功] 镜像推送成功

echo.
echo ========================================
echo   部署准备完成!
echo ========================================
echo.
echo 下一步操作:
echo.
echo 1. 访问 Sealos Cloud: https://cloud.sealos.io
echo.
echo 2. 点击 "应用管理" - "应用" - "创建应用"
echo.
echo 3. 配置应用:
echo    应用名称：%APP_NAME%
echo    镜像：%DOCKER_USERNAME%/%APP_NAME%:latest
echo    CPU: 0.5 Core
echo    内存：512 MiB (建议 1GB+)
echo    容器端口：8501
echo.
echo 4. 添加环境变量:
if not "%DASHSCOPE_API_KEY%"=="" (
    echo    DASHSCOPE_API_KEY=%DASHSCOPE_API_KEY%
) else (
    echo    DASHSCOPE_API_KEY=sk-你的 API 密钥
)
echo    STREAMLIT_SERVER_PORT=8501
echo.
echo 5. 创建域名并点击 "创建"
echo.
echo 部署完成后，你的应用将在以下域名可访问:
echo    https://%APP_NAME%-xxx.sealos.run
echo.
echo ========================================
pause
