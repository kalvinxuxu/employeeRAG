# Sealos Cloud 部署指南

> 📝 本指南将帮助你如何将 PDF 智能问答系统部署到 Sealos Cloud，并通过公开域名访问。

---

## 前置准备

### 1. 注册 Sealos 账号
- 访问 https://cloud.sealos.io
- 使用 GitHub 或邮箱注册登录

### 2. 准备 API Key
- 确保你有阿里云 DashScope API Key（用于 Qwen 模型）
- 获取地址：https://dashscope.console.aliyun.com/apiKey

### 3. 安装 Docker（可选，用于本地构建）
- Windows/Mac: https://www.docker.com/products/docker-desktop
- 安装后启动 Docker Desktop

---

## 🚀 快速部署（推荐）

### 方式 A：使用一键部署脚本

**Windows 用户：**
```bash
# 双击运行或在命令行执行
quick-deploy.bat
```

**Linux/Mac 用户：**
```bash
chmod +x quick-deploy.sh
./quick-deploy.sh
```

脚本将自动完成：
1. ✅ 检查 Docker 环境
2. ✅ 构建 Docker 镜像
3. ✅ 推送到 Docker Hub
4. ✅ 生成部署指南

### 方式 B：手动部署

#### 步骤 1：构建并推送 Docker 镜像

```bash
# 1. 构建 Docker 镜像
docker build -t your-dockerhub-username/pdf-qa-system:latest .

# 2. 登录 Docker Hub
docker login

# 3. 推送镜像到 Docker Hub
docker push your-dockerhub-username/pdf-qa-system:latest
```

> 如果没有 Docker Hub 账号，可以使用 [Docker Hub](https://hub.docker.com) 免费注册

#### 步骤 2：在 Sealos Cloud 创建应用

1. **登录 Sealos Cloud**
   - 访问 https://cloud.sealos.io

2. **进入应用管理**
   - 点击左侧菜单「应用管理」→ 「应用」
   - 点击「创建应用」

3. **配置应用**

   | 配置项 | 值 |
   |--------|-----|
   | 应用名称 | `pdf-qa-system` |
   | 镜像来源 | Docker Hub |
   | 镜像名称 | `your-dockerhub-username/pdf-qa-system:latest` |
   | CPU | `0.5 Core` (或更高) |
   | 内存 | `512 MiB` (建议 1GB+) |
   | 实例数 | `1` |

4. **配置环境变量**

   点击「添加环境变量」，添加以下变量：

   | 变量名 | 值 | 说明 |
   |--------|-----|------|
   | `DASHSCOPE_API_KEY` | `sk-xxx` | 阿里云 DashScope API 密钥 |
   | `STREAMLIT_SERVER_PORT` | `8501` | Streamlit 服务端口 |

5. **配置端口**

   | 配置项 | 值 |
   |--------|-----|
   | 容器端口 | `8501` |
   | 协议 | `HTTP` |

6. **配置公开访问**

   - 点击「创建域名」
   - 输入自定义域名（可选），或使用 Sealos 提供的免费域名
   - 域名格式：`your-app-name.xxx.sealos.run`

7. **部署应用**
   - 点击「创建」按钮
   - 等待部署完成（约 2-5 分钟）

---

### 方法 2：使用 Sealos 源码部署（更简单）

#### 步骤 1：准备 GitHub 仓库

```bash
# 1. 初始化 git 仓库（如果还没有）
git init
git add .
git commit -m "Initial commit"

# 2. 创建 GitHub 仓库并推送
git remote add origin https://github.com/your-username/pdf-qa-system.git
git push -u origin main
```

#### 步骤 2：在 Sealos 中配置源码部署

1. **访问 Sealos Cloud**
   - https://cloud.sealos.io

2. **创建应用**
   - 应用管理 → 应用 → 创建应用

3. **选择源码部署**
   - 部署方式选择「GitHub」
   - 授权并选择你的仓库

4. **配置构建选项**

   | 配置项 | 值 |
   |--------|-----|
   | 构建方式 | Dockerfile |
   | Dockerfile 路径 | `/Dockerfile` |
   | 上下文路径 | `/` |

5. **配置运行环境**
   - 添加环境变量 `DASHSCOPE_API_KEY`
   - 配置端口 `8501`

6. **创建公开域名**
   - 启用「公开访问」
   - 配置域名

---

## 上传 PDF 文档

部署完成后，你需要上传 PDF 文档到系统：

### 方式 1：通过 Sealos 文件管理

1. 在 Sealos Cloud 中，进入你的应用
2. 点击「存储」→ 「添加存储」
3. 创建一个持久化存储卷（用于存放 `data/` 和 `chroma_db/`）
4. 通过 Sealos 的文件管理功能上传 PDF 到 `data/` 目录

### 方式 2：本地构建时包含 PDF

```bash
# 将 PDF 文件放入 data 目录
mkdir -p data
cp your-document.pdf data/

# 重新构建镜像
docker build -t your-username/pdf-qa-system:latest .
docker push your-username/pdf-qa-system:latest

# 在 Sealos 中重新部署
```

### 方式 3：使用 Sealos 终端

1. 在 Sealos 应用详情中，点击「终端」
2. 使用 `curl` 或 `wget` 下载 PDF 文件：
   ```bash
   curl -o data/your-doc.pdf "https://example.com/your-doc.pdf"
   ```

---

## 初始化向量数据库

上传 PDF 后，需要初始化向量数据库：

1. **通过 Sealos 终端执行**：
   ```bash
   cd /app
   python ingest.py
   ```

2. **或者重新构建镜像**（自动执行初始化）：
   修改 `Dockerfile`，在末尾添加：
   ```dockerfile
   RUN python ingest.py
   ```

---

## 访问你的 QA 系统

部署完成后，你将获得一个公开域名：

```
https://pdf-qa-system-xxx.sealos.run
```

在浏览器中打开该域名，即可访问你的 PDF 智能问答系统！

---

## 故障排查

### 1. 应用无法启动

```bash
# 查看日志
在 Sealos 控制台 → 应用详情 → 日志

# 常见问题：
# - API Key 未配置
# - 端口配置错误
# - 依赖安装失败
```

### 2. PDF 无法上传

- 检查存储卷是否正确挂载
- 确认 `data/` 目录有写入权限
- 检查文件大小限制

### 3. 问答无响应

- 检查 `DASHSCOPE_API_KEY` 是否正确
- 确认向量数据库已初始化（`chroma_db/` 有数据）
- 查看应用日志中的错误信息

---

## 费用说明

Sealos Cloud 计费（参考）：

| 资源配置 | 预估费用 |
|----------|----------|
| 0.5 Core + 512MB | ~¥15/月 |
| 1 Core + 1GB | ~¥30/月 |
| 2 Core + 2GB | ~¥60/月 |

> 具体价格以 Sealos 官方为准，新用户通常有免费额度

---

## 优化建议

1. **启用持久化存储**
   - 为 `chroma_db/` 和 `data/` 配置持久卷
   - 避免容器重启后数据丢失

2. **配置自动扩缩容**
   - 根据访问量自动调整实例数
   - 节省成本的同时保证可用性

3. **添加 HTTPS 证书**
   - Sealos 默认证书
   - 或配置自定义域名 + Let's Encrypt
