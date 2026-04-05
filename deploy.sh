#!/bin/bash
# 阿里云轻量应用服务器一键部署脚本
# 使用方法：在服务器上运行 curl -O 上传此脚本后，执行 bash deploy.sh

set -e

echo "=========================================="
echo "  阿里云轻量应用服务器 - Streamlit 部署脚本"
echo "=========================================="

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 检查是否 root 用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 root 用户运行此脚本${NC}"
    exit 1
fi

# 1. 系统更新
echo -e "${YELLOW}[1/8] 更新系统...${NC}"
apt update && apt upgrade -y

# 2. 安装 Python
echo -e "${YELLOW}[2/8] 安装 Python3...${NC}"
apt install -y python3 python3-pip python3-venv git

# 3. 创建项目目录
echo -e "${YELLOW}[3/8] 创建项目目录...${NC}"
mkdir -p /root/myapp && cd /root/myapp

# 4. 创建虚拟环境
echo -e "${YELLOW}[4/8] 创建 Python 虚拟环境...${NC}"
python3 -m venv venv
source venv/bin/activate

# 5. 安装依赖
echo -e "${YELLOW}[5/8] 安装 Python 依赖（使用清华镜像源）...${NC}"
pip3 install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 6. 配置环境变量
echo -e "${YELLOW}[6/8] 配置环境变量...${NC}"
if [ ! -f .env ]; then
    cat > .env << 'EOF'
DASHSCOPE_API_KEY=你的通义千问 API 密钥
EOF
    echo -e "${RED}请编辑 /root/myapp/.env 文件，填入你的 DASHSCOPE_API_KEY${NC}"
else
    echo "环境变量文件已存在"
fi

# 7. 配置防火墙
echo -e "${YELLOW}[7/8] 配置防火墙...${NC}"
apt install -y ufw
ufw allow 8501/tcp
ufw allow 22/tcp
echo "y" | ufw enable

# 8. 启动应用
echo -e "${YELLOW}[8/8] 启动 Streamlit 应用...${NC}"
pkill -f streamlit || true
nohup streamlit run app.py --server.port=8501 --server.address=0.0.0.0 > app.log 2>&1 &
sleep 3

# 获取服务器公网 IP
PUBLIC_IP=$(curl -s ifconfig.me)

echo ""
echo "=========================================="
echo -e "${GREEN}  部署完成！${NC}"
echo "=========================================="
echo ""
echo "  访问地址：http://${PUBLIC_IP}:8501"
echo ""
echo "  常用命令："
echo "  - 查看状态：ps aux | grep streamlit"
echo "  - 查看日志：tail -f app.log"
echo "  - 重启应用：bash /root/myapp/restart.sh"
echo ""
echo "  下次登录服务器后执行："
echo "  cd /root/myapp && source venv/bin/activate"
echo ""
echo "=========================================="
