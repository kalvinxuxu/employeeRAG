# 阿里云轻量应用服务器部署指南

## 一、购买与准备

### 1. 购买服务器
- 访问：[阿里云轻量应用服务器](https://www.aliyun.com/product/swas)
- 推荐配置：2 核 2GB，Ubuntu 22.04
- 地域：选离你近的（杭州/上海/深圳）

### 2. 获取服务器信息
购买后在控制台找到：
- **公网 IP**
- **root 密码**（或设置 SSH 密钥）

---

## 二、本地上传代码

### 方式 A：使用 Git（推荐）

```bash
# 在服务器上执行
git clone <你的 GitHub 仓库地址>
cd claude_internalQAsystem
```

### 方式 B：使用 SCP 上传

```bash
# 在本地 PowerShell 执行
scp -r ./* root@<服务器 IP>:/root/myapp
```

---

## 三、一键部署脚本

### 在服务器上执行以下命令：

```bash
# 1. 更新系统
apt update && apt upgrade -y

# 2. 安装 Python3 和 pip
apt install -y python3 python3-pip python3-venv

# 3. 创建项目目录
mkdir -p /root/myapp && cd /root/myapp

# 4. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 5. 安装依赖
pip3 install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 6. 配置环境变量
cat > .env << 'EOF'
DASHSCOPE_API_KEY=你的通义千问 API 密钥
EOF

# 7. 开放防火墙端口
ufw allow 8501/tcp
ufw allow 22/tcp
ufw --force enable

# 8. 后台运行 Streamlit
nohup streamlit run app.py --server.port=8501 --server.address=0.0.0.0 > app.log 2>&1 &

# 9. 查看运行状态
ps aux | grep streamlit
tail -f app.log
```

---

## 四、访问应用

浏览器打开：`http://<你的服务器 IP>:8501`

---

## 五、常用命令

```bash
# 查看应用是否运行
ps aux | grep streamlit

# 重启应用
pkill -f streamlit
source venv/bin/activate
nohup streamlit run app.py --server.port=8501 --server.address=0.0.0.0 > app.log 2>&1 &

# 查看日志
tail -f app.log

# 停止应用
pkill -f streamlit

# 进入虚拟环境
source venv/bin/activate

# 退出虚拟环境
deactivate
```

---

## 六、域名绑定（可选）

### 1. 在阿里云购买域名
- 访问 [阿里云域名](https://wanwang.aliyun.com/domain)

### 2. 添加 A 记录
- 登录域名控制台
- 添加解析记录：
  - 类型：A
  - 主机记录：`www` 或 `@`
  - 记录值：你的服务器 IP

### 3. Nginx 反向代理

```bash
# 安装 Nginx
apt install -y nginx

# 配置反向代理
cat > /etc/nginx/sites-available/myapp << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
EOF

# 启用配置
ln -s /etc/nginx/sites-available/myapp /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
```

---

## 七、开机自启动（可选）

```bash
# 创建 systemd 服务
cat > /etc/systemd/system/streamlit-app.service << 'EOF'
[Unit]
Description=Streamlit RAG App
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/root/myapp
ExecStart=/root/myapp/venv/bin/streamlit run app.py --server.port=8501 --server.address=0.0.0.0
Restart=always

[Install]
WantedBy=multi-user.target
EOF

# 启用服务
systemctl daemon-reload
systemctl enable streamlit-app
systemctl start streamlit-app
systemctl status streamlit-app
```

---

## 八、故障排查

| 问题 | 解决方案 |
|------|----------|
| 无法访问 8501 端口 | 检查阿里云安全组，确保 8501 端口已开放 |
| 应用崩溃 | 查看 `tail -f app.log` |
| 内存不足 | 升级服务器配置或添加 swap 分区 |
| API 调用失败 | 检查 `.env` 文件中的 API 密钥 |

---

## 九、成本估算

| 项目 | 价格 |
|------|------|
| 轻量服务器 (2 核 2GB) | ~99 元/年 |
| 域名（可选） | ~60 元/年 |
| 通义千问 API | 按 token 计费 |
| **合计** | **~160 元/年** |
