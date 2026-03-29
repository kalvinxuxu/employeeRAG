#!/bin/bash

# Sealos Cloud 快速部署脚本
# 使用前请修改下面的配置变量

# ==================== 配置区域 ====================

# Docker Hub 用户名 (需要注册 https://hub.docker.com)
DOCKER_USERNAME="your-dockerhub-username"

# 应用名称 (将用于域名：pdf-qa-system-xxx.sealos.run)
APP_NAME="pdf-qa-system"

# 阿里云 DashScope API Key
DASHSCOPE_API_KEY="sk-your-api-key-here"

# ==================== 自动执行区域 ====================

echo "========================================"
echo "  Sealos Cloud 快速部署工具"
echo "========================================"
echo ""

# 1. 构建 Docker 镜像
echo "[1/3] 构建 Docker 镜像..."
docker build -t ${DOCKER_USERNAME}/${APP_NAME}:latest .

if [ $? -ne 0 ]; then
    echo "[错误] 镜像构建失败"
    exit 1
fi
echo "[成功] 镜像构建完成"
echo ""

# 2. 登录 Docker Hub
echo "[2/3] 登录 Docker Hub..."
docker login

if [ $? -ne 0 ]; then
    echo "[错误] Docker Hub 登录失败"
    exit 1
fi
echo ""

# 3. 推送镜像
echo "[3/3] 推送镜像到 Docker Hub..."
docker push ${DOCKER_USERNAME}/${APP_NAME}:latest

if [ $? -ne 0 ]; then
    echo "[错误] 镜像推送失败"
    exit 1
fi
echo "[成功] 镜像推送成功"

echo ""
echo "========================================"
echo "  部署完成!"
echo "========================================"
echo ""
echo "下一步操作:"
echo ""
echo "1. 访问 https://cloud.sealos.io 并登录"
echo "2. 点击 '应用管理' -> '应用' -> '创建应用'"
echo "3. 配置应用:"
echo "   - 应用名称：${APP_NAME}"
echo "   - 镜像：${DOCKER_USERNAME}/${APP_NAME}:latest"
echo "   - CPU: 0.5 Core, 内存：512 MiB"
echo "   - 容器端口：8501"
echo "4. 添加环境变量:"
echo "   - DASHSCOPE_API_KEY=${DASHSCOPE_API_KEY}"
echo "5. 创建域名并部署"
echo ""
echo "部署完成后，你的应用将在以下域名可访问:"
echo "   https://${APP_NAME}-xxx.sealos.run"
echo ""
