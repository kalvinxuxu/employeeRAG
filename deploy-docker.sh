#!/bin/bash
# 阿里云 Docker 一键部署脚本
# 使用方法：ssh 登录服务器后，执行 bash deploy-docker.sh

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  阿里云 Docker 一键部署脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查是否 root 用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 root 用户运行此脚本${NC}"
    exit 1
fi

# 检查 Docker 是否已安装
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}[1/6] 安装 Docker...${NC}"
    curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
    echo -e "${GREEN}✓ Docker 安装完成${NC}"
else
    echo -e "${GREEN}✓ Docker 已安装${NC}"
fi

# 配置镜像加速
echo -e "${YELLOW}[2/6] 配置 Docker 镜像加速...${NC}"
mkdir -p /etc/docker
cat > /etc/docker/daemon.json << 'EOF'
{
  "registry-mirrors": [
    "https://docker.m.daocloud.io",
    "https://docker.1panel.live",
    "https://hub.uuuadc.top"
  ]
}
EOF
systemctl daemon-reload
systemctl restart docker
echo -e "${GREEN}✓ Docker 镜像加速配置完成${NC}"

# 安装 Git
echo -e "${YELLOW}[3/6] 安装 Git...${NC}"
apt install -y git > /dev/null 2>&1
echo -e "${GREEN}✓ Git 安装完成${NC}"

# 拉取代码
echo -e "${YELLOW}[4/6] 拉取项目代码...${NC}"
if [ -d "/root/rag-app" ]; then
    echo "项目目录已存在，跳过克隆"
else
    echo -e "${RED}请手动克隆你的仓库到 /root/rag-app${NC}"
    echo "例如：git clone https://github.com/yourname/yourrepo /root/rag-app"
    exit 1
fi
cd /root/rag-app
echo -e "${GREEN}✓ 代码拉取完成${NC}"

# 创建数据目录
echo -e "${YELLOW}[5/6] 创建数据目录...${NC}"
mkdir -p /root/rag-app/chroma_db /root/rag-app/data
echo -e "${GREEN}✓ 数据目录创建完成${NC}"

# 配置环境变量
echo -e "${YELLOW}[6/6] 配置环境变量...${NC}"
if [ -f "/root/rag-app/.env" ]; then
    echo "环境变量文件已存在"
else
    cat > /root/rag-app/.env << 'EOF'
DASHSCOPE_API_KEY=你的通义千问 API 密钥
EOF
    echo -e "${RED}请编辑 /root/rag-app/.env 文件，填入你的 DASHSCOPE_API_KEY${NC}"
fi

# 构建 Docker 镜像
echo ""
echo -e "${BLUE}开始构建 Docker 镜像...${NC}"
docker build -t rag-app:latest .

# 停止并删除旧容器（如果存在）
echo ""
echo -e "${BLUE}部署容器...${NC}"
docker rm -f rag-app 2>/dev/null || true

# 启动容器
docker run -d \
  --name rag-app \
  -p 8501:8501 \
  -v /root/rag-app/chroma_db:/app/chroma_db \
  -v /root/rag-app/data:/app/data \
  -v /root/rag-app/.env:/app/.env \
  --restart always \
  rag-app:latest

# 等待容器启动
sleep 3

# 获取服务器 IP
PUBLIC_IP=$(curl -s ifconfig.me)

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  部署完成！${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "  访问地址：http://${PUBLIC_IP}:8501"
echo ""
echo -e "${YELLOW}  重要提醒：${NC}"
echo "  1. 在阿里云控制台防火墙开放 8501 端口"
echo "  2. 编辑 .env 文件填入你的 DASHSCOPE_API_KEY"
echo ""
echo -e "${YELLOW}  常用命令：${NC}"
echo "  - 查看状态：docker ps"
echo "  - 查看日志：docker logs -f rag-app"
echo "  - 重启应用：docker restart rag-app"
echo "  - 停止应用：docker stop rag-app"
echo ""
echo -e "${GREEN}========================================${NC}"
