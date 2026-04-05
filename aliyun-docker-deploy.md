# 阿里云 Docker 部署完整指南

## 准备工作

### 1. 购买服务器
- 访问 [阿里云轻量应用服务器](https://www.aliyun.com/product/swas)
- 选择：**Ubuntu 22.04**、**2 核 2GB**
- 地域：选离你近的（华东 2-上海 / 华南 1-深圳等）

### 2. 获取服务器信息
购买后在控制台找到：
- **公网 IP 地址**
- **root 密码**（首次登录会要求设置）

### 3. 准备 API 密钥
确保你有通义千问 API 密钥（DashScope）：
- 访问：https://dashscope.console.aliyun.com/
- 创建 API Key

---

## 部署步骤（复制粘贴执行）

### 第 1 步：SSH 登录服务器

在本地 PowerShell 或 CMD 执行：
```bash
ssh root@<你的服务器 IP>
```
输入密码登录（输入时不显示，正常）。

---

### 第 2 步：安装 Docker

登录后执行：
```bash
# 使用国内镜像源快速安装 Docker
curl -fsSL https://get.docker.com | bash -s docker --mirror Aliyun
```

等待安装完成（约 1-2 分钟）。

---

### 第 3 步：配置 Docker 镜像加速

```bash
# 配置阿里云镜像加速器
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

# 重启 Docker 使配置生效
systemctl daemon-reload
systemctl restart docker

# 验证配置
docker info | grep "Registry Mirrors"
```

---

### 第 4 步：拉取项目代码

```bash
# 安装 Git
apt install -y git

# 克隆你的仓库（替换为你的仓库地址）
git clone <你的 GitHub 仓库地址> /root/rag-app
cd /root/rag-app
```

---

### 第 5 步：构建 Docker 镜像

```bash
# 构建镜像（约 3-5 分钟）
docker build -t rag-app:latest .
```

---

### 第 6 步：运行 Docker 容器

```bash
# 创建必要的数据目录
mkdir -p /root/rag-app/chroma_db /root/rag-app/data

# 创建 .env 文件（替换你的 API 密钥）
cat > /root/rag-app/.env << 'EOF'
DASHSCOPE_API_KEY=你的通义千问 API 密钥
EOF
```

**⚠️ 重要：编辑上面的 `.env` 文件，填入你的真实 API 密钥！**

```bash
# 启动容器
docker run -d \
  --name rag-app \
  -p 8501:8501 \
  -v /root/rag-app/chroma_db:/app/chroma_db \
  -v /root/rag-app/data:/app/data \
  -v /root/rag-app/.env:/app/.env \
  --restart always \
  rag-app:latest
```

---

### 第 7 步：配置阿里云防火墙

**在阿里云控制台操作：**
1. 登录 [阿里云轻量应用服务器控制台](https://swas.console.aliyun.com/)
2. 点击你的服务器卡片
3. 点击左侧 **防火墙**
4. 点击 **添加规则**
5. 填写：
   - 端口：`8501`
   - 协议：`TCP`
6. 点击确定

---

### 第 8 步：访问应用

浏览器打开：
```
http://<你的服务器 IP>:8501
```

---

## 常用命令

### 查看容器状态
```bash
docker ps
```

### 查看应用日志
```bash
docker logs -f rag-app
```

### 重启应用
```bash
docker restart rag-app
```

### 停止应用
```bash
docker stop rag-app
```

### 启动应用
```bash
docker start rag-app
```

### 进入容器内部
```bash
docker exec -it rag-app bash
```

### 查看容器资源占用
```bash
docker stats rag-app
```

---

## 一键部署脚本

你也可以直接运行这个脚本自动完成所有步骤：

```bash
# 在服务器上执行
curl -O https://raw.githubusercontent.com/<你的用户名>/<你的仓库>/main/deploy-docker.sh
chmod +x deploy-docker.sh
bash deploy-docker.sh
```

---

## 故障排查

### 问题 1：无法访问 8501 端口

**检查防火墙：**
```bash
# 在服务器上检查端口监听
netstat -tlnp | grep 8501

# 检查 Docker 容器是否运行
docker ps | grep rag-app
```

**解决：** 确保阿里云控制台防火墙已开放 8501 端口。

### 问题 2：容器启动失败

```bash
# 查看容器日志
docker logs rag-app

# 查看容器详情
docker inspect rag-app
```

### 问题 3：API 调用失败

```bash
# 进入容器检查 .env 文件
docker exec -it rag-app cat /app/.env
```

确保 `.env` 文件中的 API 密钥正确。

### 问题 4：内存不足

```bash
# 查看内存使用
free -h

# 如果内存不足，可以添加 swap
dd if=/dev/zero of=/swapfile bs=1M count=2048
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
```

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

## 成本估算

| 项目 | 价格 |
|------|------|
| 阿里云轻量服务器 (2 核 2GB) | ~99 元/年 |
| 通义千问 API | 按 token 计费（约 0.008 元/千 tokens） |
| **合计** | **约 100-200 元/年**（小规模使用） |

---

## 升级配置

如果以后不够用：
1. 登录阿里云控制台
2. 点击 **升级配置**
3. 选择更高配置（4GB/8GB 内存）
4. 支付差价即可

---

## 总结

部署完成后：
- ✅ 应用 24 小时运行
- ✅ 任何人有 URL 都能访问
- ✅ 数据持久化保存
- ✅ 自动重启（`--restart always`）

**祝你部署顺利！有任何问题随时问。**
