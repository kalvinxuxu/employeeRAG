#!/bin/bash

# 一站式快速部署准备脚本
# 自动完成：检查环境 → 配置 Docker Hub → 构建镜像 → 推送 → 生成部署指南

echo "=========================================="
echo "  🚀 Sealos Cloud 一键部署准备工具"
echo "=========================================="
echo ""

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查 Docker 是否安装
check_docker() {
    if ! command -v docker &> /dev/null; then
        echo -e "${RED}❌ Docker 未安装${NC}"
        echo "请先安装 Docker Desktop: https://www.docker.com/products/docker-desktop"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker 已安装：$(docker --version)${NC}"
}

# 检查 Docker 是否运行
check_docker_running() {
    if ! docker info &> /dev/null; then
        echo -e "${RED}❌ Docker 未运行${NC}"
        echo "请启动 Docker Desktop"
        exit 1
    fi
    echo -e "${GREEN}✅ Docker 正在运行${NC}"
}

# 获取用户配置
get_user_config() {
    echo ""
    echo "📋 请输入以下配置信息："
    echo ""

    # Docker Hub 用户名
    read -p "Docker Hub 用户名 (例如：kalvi): " DOCKER_USERNAME
    if [ -z "$DOCKER_USERNAME" ]; then
        echo -e "${RED}用户名不能为空${NC}"
        exit 1
    fi

    # 应用名称
    read -p "应用名称 (默认：pdf-qa-system): " APP_NAME
    if [ -z "$APP_NAME" ]; then
        APP_NAME="pdf-qa-system"
    fi

    # API Key
    read -p "DashScope API Key (sk-开头，可选): " DASHSCOPE_API_KEY

    echo ""
    echo -e "${YELLOW}⚙️  配置信息:${NC}"
    echo "   Docker Hub 用户名：$DOCKER_USERNAME"
    echo "   应用名称：$APP_NAME"
    echo "   API Key: ${DASHSCOPE_API_KEY:0:10}...${DASHSCOPE_API_KEY: -5}"
    echo ""

    read -p "确认配置是否正确？(y/n): " confirm
    if [ "$confirm" != "y" ]; then
        echo "已取消"
        exit 1
    fi

    # 更新部署脚本中的配置
    if [ -f "deploy-sealos.sh" ]; then
        sed -i.bak "s/DOCKER_USERNAME=\".*\"/DOCKER_USERNAME=\"$DOCKER_USERNAME\"/" deploy-sealos.sh
        sed -i.bak "s/APP_NAME=\".*\"/APP_NAME=\"$APP_NAME\"/" deploy-sealos.sh
        sed -i.bak "s|DASHSCOPE_API_KEY=\".*\"|DASHSCOPE_API_KEY=\"$DASHSCOPE_API_KEY\"|" deploy-sealos.sh
        rm deploy-sealos.sh.bak 2>/dev/null
        echo -e "${GREEN}✅ 已更新部署脚本配置${NC}"
    fi
}

# 构建镜像
build_image() {
    echo ""
    echo "📦 开始构建 Docker 镜像..."
    docker build -t ${DOCKER_USERNAME}/${APP_NAME}:latest .

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 镜像构建成功${NC}"
    else
        echo -e "${RED}❌ 镜像构建失败${NC}"
        exit 1
    fi
}

# 推送镜像
push_image() {
    echo ""
    echo "🔐 登录 Docker Hub..."
    docker login

    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Docker Hub 登录失败${NC}"
        exit 1
    fi

    echo ""
    echo "📤 推送镜像到 Docker Hub..."
    docker push ${DOCKER_USERNAME}/${APP_NAME}:latest

    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 镜像推送成功${NC}"
    else
        echo -e "${RED}❌ 镜像推送失败${NC}"
        exit 1
    fi
}

# 生成部署指南
generate_guide() {
    echo ""
    echo "=========================================="
    echo "  ✅ 部署准备完成！"
    echo "=========================================="
    echo ""
    echo -e "${GREEN}📋 下一步操作：${NC}"
    echo ""
    echo "1️⃣  访问 Sealos Cloud: https://cloud.sealos.io"
    echo ""
    echo "2️⃣  点击「应用管理」→「应用」→「创建应用」"
    echo ""
    echo "3️⃣  配置应用："
    echo "   ┌─────────────────────────────────────────┐"
    echo "   │ 应用名称：  ${APP_NAME}"
    echo "   │ 镜像：      ${DOCKER_USERNAME}/${APP_NAME}:latest"
    echo "   │ CPU:        0.5 Core"
    echo "   │ 内存：512 MiB (建议 1GB+)"
    echo "   │ 容器端口：  8501"
    echo "   └─────────────────────────────────────────┘"
    echo ""
    echo "4️⃣  添加环境变量："
    echo "   ┌─────────────────────────────────────────┐"
    if [ -n "$DASHSCOPE_API_KEY" ]; then
        echo "   │ DASHSCOPE_API_KEY = ${DASHSCOPE_API_KEY:0:10}...${DASHSCOPE_API_KEY: -5}"
    else
        echo "   │ DASHSCOPE_API_KEY = sk-你的 API 密钥"
    fi
    echo "   │ STREAMLIT_SERVER_PORT = 8501"
    echo "   └─────────────────────────────────────────┘"
    echo ""
    echo "5️⃣  创建域名并点击「创建」"
    echo ""
    echo -e "${YELLOW}🌐 部署完成后，你的应用将在以下域名可访问：${NC}"
    echo "   https://${APP_NAME}-xxx.sealos.run"
    echo ""
    echo "=========================================="
    echo ""
}

# 主流程
main() {
    check_docker
    check_docker_running
    get_user_config
    build_image
    push_image
    generate_guide
}

# 运行主流程
main
