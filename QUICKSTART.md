# 🚀 快速部署到 Sealos Cloud

> 5 分钟将你的 PDF 问答系统部署到云端，获得公开访问域名

---

## 📋 部署清单

开始前请确保你已准备：

- [ ] Docker 已安装并运行
- [ ] Docker Hub 账号（https://hub.docker.com）
- [ ] Sealos Cloud 账号（https://cloud.sealos.io）
- [ ] 阿里云 DashScope API Key（https://dashscope.console.aliyun.com/apiKey）

---

## 步骤 1：构建并推送 Docker 镜像

### Windows 用户

双击运行 `deploy-sealos.bat` 或在命令行执行：

```bash
deploy-sealos.bat
```

### Linux/Mac 用户

```bash
chmod +x deploy-sealos.sh
./deploy-sealos.sh
```

### 或手动执行

```bash
# 1. 构建镜像
docker build -t your-username/pdf-qa-system:latest .

# 2. 登录 Docker Hub
docker login

# 3. 推送镜像
docker push your-username/pdf-qa-system:latest
```

---

## 步骤 2：在 Sealos Cloud 创建应用

### 2.1 登录并进入应用管理

1. 访问 https://cloud.sealos.io 并登录
2. 点击左侧菜单「应用管理」→「应用」
3. 点击「创建应用」

### 2.2 配置应用

| 配置项 | 值 |
|--------|-----|
| **应用名称** | `pdf-qa-system` |
| **镜像来源** | Docker Hub |
| **镜像名称** | `your-username/pdf-qa-system:latest` |
| **CPU** | `0.5 Core` |
| **内存** | `512 MiB` (建议 1GB+) |
| **实例数** | `1` |

### 2.3 配置环境变量

点击「添加环境变量」：

| 变量名 | 值 | 说明 |
|--------|-----|------|
| `DASHSCOPE_API_KEY` | `sk-xxx` | 阿里云 API 密钥 |
| `STREAMLIT_SERVER_PORT` | `8501` | 服务端口 |

### 2.4 配置端口

| 配置项 | 值 |
|--------|-----|
| **容器端口** | `8501` |
| **协议** | `HTTP` |

### 2.5 配置公开访问

1. 点击「创建域名」
2. 使用 Sealos 提供的免费域名：`pdf-qa-system-xxx.sealos.run`
3. 或绑定自定义域名

### 2.6 完成部署

点击「创建」按钮，等待 2-5 分钟完成部署。

---

## 步骤 3：上传 PDF 文档

### 方式 A：通过 Sealos 终端上传

1. 在应用详情中点击「终端」
2. 执行命令下载 PDF：

```bash
curl -o data/your-doc.pdf "https://example.com/your-doc.pdf"
```

### 方式 B：本地包含 PDF

```bash
# 将 PDF 放入 data/ 目录
mkdir -p data
cp your-document.pdf data/

# 重新构建并推送
docker build -t your-username/pdf-qa-system:latest .
docker push your-username/pdf-qa-system:latest

# 在 Sealos 中重新部署
```

---

## 步骤 4：初始化向量数据库

在 Sealos 应用终端中执行：

```bash
cd /app
python ingest.py
```

等待索引完成后，你的系统就可以使用了！

---

## ✅ 完成！

在浏览器中打开你的域名：

```
https://pdf-qa-system-xxx.sealos.run
```

现在你可以：
- 📄 上传 PDF 文档
- 💬 与 AI 进行问答
- 🔗 查看引用来源

---

## 💰 费用说明

| 资源配置 | 月费用 |
|----------|--------|
| 0.5 Core + 512MB | ~¥15 |
| 1 Core + 1GB | ~¥30 |
| 2 Core + 2GB | ~¥60 |

> 新用户通常有免费额度，具体以 Sealos 官方为准

---

## 🔧 常见问题

### 应用无法启动？
- 检查日志：Sealos 控制台 → 应用详情 → 日志
- 确认 API Key 正确
- 检查端口配置为 8501

### PDF 无法上传？
- 检查存储卷是否挂载
- 确认 `data/` 目录有写入权限

### 问答无响应？
- 确认 `DASHSCOPE_API_KEY` 有效
- 检查 `chroma_db/` 是否有数据
- 查看应用日志

---

## 📚 更多文档

- 详细部署指南：[sealos-deploy.md](sealos-deploy.md)
- 本地使用：[README.md](README.md)
- 功能说明：[FEATURES_P1.md](FEATURES_P1.md)
