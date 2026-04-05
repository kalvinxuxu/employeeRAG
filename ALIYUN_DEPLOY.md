# 阿里云部署完整指南

## 目录

1. [快速开始](#快速开始)
2. [方案选择](#方案选择)
3. [Docker 部署（推荐）](#docker-部署推荐)
4. [Ubuntu 原生部署](#ubuntu-原生部署)
5. [常见问题](#常见问题)

---

## 快速开始

### 准备工作

| 项目 | 说明 |
|------|------|
| **服务器** | 阿里云轻量应用服务器（Ubuntu 22.04，2 核 2GB） |
| **API 密钥** | 通义千问 API Key（https://dashscope.console.aliyun.com/） |
| **代码** | 项目代码已上传到 Git 仓库 |

### 3 分钟快速部署

```bash
# 1. SSH 登录服务器
ssh root@<你的服务器 IP>

# 2. 安装 Docker
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 3. 拉取代码
git clone <你的仓库地址> /root/rag-app && cd /root/rag-app

# 4. 配置 API 密钥
echo "DASHSCOPE_API_KEY=你的 API 密钥" > .env

# 5. 构建并运行
docker build -t rag-app . && docker run -d --name rag-app -p 8501:8501 --restart always rag-app
```

### 开放防火墙

在阿里云控制台：
1. 进入服务器详情 → **防火墙**
2. 添加规则：端口 `8501`，协议 `TCP`

### 访问应用

浏览器打开：`http://<你的服务器 IP>:8501`

---

## 方案选择

| 方案 | 优点 | 缺点 | 适合场景 |
|------|------|------|----------|
| **Docker 部署** | 环境隔离、易迁移、干净 | 需学 Docker 命令 | 生产环境、多项目 |
| **Ubuntu 原生** | 简单直观、调试方便 | 环境污染、依赖冲突 | 开发测试、单项目 |
| **Sealos** | 最简单、无需管理服务器 | 按量计费、国内访问一般 | 快速 Demo、临时展示 |

**推荐：Docker 部署** - 你的项目已有 Dockerfile，直接用最方便。

---

## Docker 部署（推荐）

### 步骤 1：购买服务器

1. 访问 [阿里云轻量应用服务器](https://www.aliyun.com/product/swas)
2. 选择配置：
   - 系统：**Ubuntu 22.04**
   - CPU/内存：**2 核 2GB**
   - 地域：**华东 2（上海）** 或离你近的
3. 设置 root 密码

### 步骤 2：SSH 登录

```bash
ssh root@<你的服务器 IP>
```

输入密码登录（输入时不显示）。

### 步骤 3：安装 Docker

```bash
# 使用阿里云镜像源快速安装
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun

# 验证安装
docker --version
```

### 步骤 4：配置 Docker 镜像加速

```bash
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
systemctl daemon-reload && systemctl restart docker
```

### 步骤 5：拉取项目代码

```bash
# 安装 Git
apt install -y git

# 克隆仓库（替换为你的地址）
git clone <你的 GitHub 仓库地址> /root/rag-app
cd /root/rag-app
```

### 步骤 6：配置环境变量

```bash
# 创建 .env 文件
cat > /root/rag-app/.env << 'EOF'
DASHSCOPE_API_KEY=你的通义千问 API 密钥
EOF

# 用 nano 编辑（可选）
nano /root/rag-app/.env
```

### 步骤 7：构建 Docker 镜像

```bash
# 构建镜像（首次约 3-5 分钟）
docker build -t rag-app:latest .
```

### 步骤 8：运行容器

```bash
docker run -d \
  --name rag-app \
  -p 8501:8501 \
  -v /root/rag-app/chroma_db:/app/chroma_db \
  -v /root/rag-app/data:/app/data \
  -v /root/rag-app/.env:/app/.env \
  --restart always \
  rag-app:latest
```

### 步骤 9：配置防火墙

在阿里云控制台：
1. 点击你的服务器
2. 左侧 **防火墙** → **添加规则**
3. 端口：`8501`，协议：`TCP`

### 步骤 10：访问应用

浏览器打开：`http://<你的服务器 IP>:8501`

---

## Ubuntu 原生部署

### 步骤 1-2：同上（购买 + SSH 登录）

### 步骤 3：安装系统依赖

```bash
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git curl
```

### 步骤 4：拉取代码

```bash
git clone <你的仓库地址> /root/rag-app
cd /root/rag-app
```

### 步骤 5：创建虚拟环境

```bash
python3 -m venv venv
source venv/bin/activate
```

### 步骤 6：安装依赖

```bash
pip install --upgrade pip
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 步骤 7：配置环境变量

```bash
cat > .env << 'EOF'
DASHSCOPE_API_KEY=你的通义千问 API 密钥
EOF
```

### 步骤 8：后台运行

```bash
nohup streamlit run app.py \
  --server.port=8501 \
  --server.address=0.0.0.0 \
  > app.log 2>&1 &
```

### 步骤 9：配置防火墙

同上（开放 8501 端口）。

### 步骤 10：访问应用

浏览器打开：`http://<你的服务器 IP>:8501`

---

## 常用命令

### Docker 方式

| 命令 | 说明 |
|------|------|
| `docker ps` | 查看运行状态 |
| `docker logs -f rag-app` | 查看实时日志 |
| `docker restart rag-app` | 重启应用 |
| `docker stop rag-app` | 停止应用 |
| `docker start rag-app` | 启动应用 |
| `docker exec -it rag-app bash` | 进入容器 |

### Ubuntu 原生方式

| 命令 | 说明 |
|------|------|
| `ps aux | grep streamlit` | 查看运行状态 |
| `tail -f app.log` | 查看实时日志 |
| `pkill -f streamlit` | 停止应用 |
| `source venv/bin/activate` | 进入虚拟环境 |

---

## 常见问题

### 1. 无法访问 8501 端口

**检查防火墙：**
```bash
# 查看端口监听
netstat -tlnp | grep 8501

# 查看容器状态
docker ps | grep rag-app
```

**解决：** 确保阿里云控制台防火墙已开放 8501 端口。

### 2. BGE 模型下载慢

**方案 A：使用国内镜像**
```bash
export HF_ENDPOINT=https://hf-mirror.com
```

**方案 B：禁用语义缓存**
编辑 `app.py`，设置 `"use_cache": False`

### 3. 容器启动失败

```bash
# 查看日志
docker logs rag-app

# 查看容器详情
docker inspect rag-app
```

### 4. 内存不足

```bash
# 查看内存
free -h

# 添加 swap
dd if=/dev/zero of=/swapfile bs=1M count=2048
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```

### 5. API 调用失败

```bash
# 检查 .env 文件
docker exec -it rag-app cat /app/.env
cat /root/rag-app/.env
```

确保 API 密钥正确且未过期。

---

## 数据备份

### 备份向量数据库

```bash
# 压缩备份
tar -czvf chroma_db_backup_$(date +%Y%m%d).tar.gz /root/rag-app/chroma_db

# 下载到本地
scp root@<服务器 IP>:/root/rag-app/chroma_db_backup_*.tar.gz ./
```

### 恢复数据

```bash
tar -xzvf chroma_db_backup_*.tar.gz -C /root/rag-app/
docker restart rag-app
```

---

## 一键部署脚本

我已创建以下脚本：

| 文件 | 用途 |
|------|------|
| `deploy-docker.sh` | Linux 一键部署脚本 |
| `deploy-docker.bat` | Windows 上传脚本 |
| `aliyun-docker-deploy.md` | 详细部署文档 |

### 使用方法

```bash
# 上传脚本到服务器
scp deploy-docker.sh root@<服务器 IP>:/root/

# 登录服务器执行
chmod +x /root/deploy-docker.sh
bash /root/deploy-docker.sh
```

---

## 成本估算

| 项目 | 价格 |
|------|------|
| 阿里云轻量服务器 (2 核 2GB) | ~99 元/年 |
| 通义千问 API | 按 token 计费（约 0.008 元/千 tokens） |
| **合计** | **约 100-200 元/年**（小规模使用） |

---

## 总结

部署完成后：
- ✅ 应用 24 小时运行
- ✅ 任何人有 URL 都能访问
- ✅ 数据持久化保存
- ✅ 自动重启（`--restart always`）

**祝你部署顺利！**
