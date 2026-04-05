@echo off
chcp 65001 > nul
echo ========================================
echo   阿里云 Docker 部署 - 文件上传脚本
echo ========================================
echo.
echo 使用说明：
echo 1. 将此脚本放在项目根目录
echo 2. 修改下面的服务器 IP 和密码
echo 3. 双击运行
echo.

set SERVER_IP=你的服务器 IP
set SERVER_USER=root

echo 正在上传文件到服务器...

:: 使用 scp 上传 deploy-docker.sh
scp deploy-docker.sh %SERVER_USER%@%SERVER_IP%:/root/

echo.
echo 上传完成！
echo.
echo 接下来请在 SSH 中执行：
echo   ssh %SERVER_USER%@%SERVER_IP%
echo   chmod +x /root/deploy-docker.sh
echo   bash /root/deploy-docker.sh
echo.
pause
