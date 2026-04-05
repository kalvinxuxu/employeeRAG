# Sealos Cloud 部署指南

## 📋 前提条件

1. 拥有一个 Docker Hub 账号
2. 已安装 Docker Desktop
3. 有阿里云 DashScope API Key

---

## 🚀 部署步骤

### 步骤 1：构建并推送 Docker 镜像

```bash
# 1. 构建镜像
docker build -t kalvinxuxu/employeeRAG:latest .

# 2. 登录 Docker Hub
docker login -u kalvinxuxu

# 3. 推送镜像
docker push kalvinxuxu/employeeRAG:latest
```

> 💡 如果 Docker Hub 账号不是 `kalvinxuxu`，请替换为你的用户名

---

### 步骤 2：在 Sealos 控制台部署

#### 2.1 登录 Sealos
1. 访问 https://sealos.run/
2. 点击 "登录"（支持 GitHub/邮箱登录）
3. 进入控制台 https://cloud.sealos.run/

#### 2.2 创建应用
1. 点击顶部菜单 **"应用管理"**
2. 点击 **"创建应用"** 按钮
3. 选择 **"镜像创建"** 模式

#### 2.3 填写配置

| 字段 | 值 |
|------|-----|
| 应用名称 | `pdf-qa-system` |
| 镜像 | `kalvinxuxu/employeeRAG:latest` |
| 镜像拉取策略 | `Always` |
| CPU 请求 | `0.5` |
| 内存请求 | `512Mi` |
| CPU 限制 | `1` |
| 内存限制 | `1Gi` |

#### 2.4 配置环境变量

点击 **"环境变量"** 添加：

| 名称 | 值 |
|------|-----|
| `DASHSCOPE_API_KEY` | `sk-你的阿里云 API Key` |

#### 2.5 配置端口和服务

1. 点击 **"服务"** 标签页
2. 点击 **"添加服务"**
3. 填写：
   - 服务名称：`pdf-qa-system-svc`
   - 服务类型：`NodePort`（暴露外网）或 `ClusterIP`（仅内网）
   - 端口：`8501` → `8501`
   - 协议：`TCP`

#### 2.6 配置健康检查（可选）

1. 点击 **"健康检查"** 标签页
2. 添加 HTTP 检查：
   - 路径：`/`
   - 端口：`8501`
   - 初始延迟：`10` 秒
   - 检测间隔：`30` 秒

#### 2.7 部署

1. 点击 **"创建"** 按钮
2. 等待应用状态变为 `Running`
3. 点击应用名称进入详情页
4. 在 **"服务"** 标签页找到访问地址

---

## 🔗 获取访问地址

部署成功后，Sealos 会提供一个公网访问地址：

```
https://pdf-qa-system-xxxxx.sealos.run
```

或者如果是 NodePort 服务：
```
http://<节点 IP>:<NodePort>
```

---

## 📁 持久化数据存储（可选）

如果需要持久化存储向量数据库和缓存：

### 在 sealos-app.yaml 中添加：

```yaml
volumes:
  - name: chroma-data
    mountPath: /app/chroma_db
    type: persistentVolumeClaim
    size: 1Gi
  - name: cache-data
    mountPath: /app/semantic_cache
    type: persistentVolumeClaim
    size: 512Mi
```

### 或在控制台操作：
1. 点击 **"存储"** 标签页
2. 添加持久化卷
3. 挂载到 `/app/chroma_db` 和 `/app/semantic_cache`

---

## 🔧 故障排查

### 问题 1：镜像拉取失败
```bash
# 检查镜像是否存在
docker pull kalvinxuxu/employeeRAG:latest

# 确认镜像已推送
docker images
```

### 问题 2：应用启动失败
1. 进入 Sealos 控制台 → 应用详情
2. 点击 **"日志"** 查看启动日志
3. 检查环境变量 `DASHSCOPE_API_KEY` 是否正确

### 问题 3：无法访问
1. 检查服务是否配置了 NodePort 或 LoadBalancer
2. 确认防火墙规则允许 8501 端口
3. 检查健康检查是否通过

---

## 💰 费用说明

Sealos 计费项：
- **计算资源**：约 ¥0.1/小时（0.5 CPU + 512MB）
- **存储空间**：约 ¥0.3/GB/月
- **网络流量**：免费额度内免费

预估月费用：**¥50-100**（根据使用量）

---

## 🎯 快速命令参考

```bash
# 本地测试 Docker 镜像
docker run -p 8501:8501 -e DASHSCOPE_API_KEY=sk-xxx kalvinxuxu/employeeRAG:latest

# 查看容器日志
docker logs -f <container_id>

# 进入容器调试
docker exec -it <container_id> bash
```

---

## 📞 技术支持

- Sealos 文档：https://sealos.run/docs/
- Sealos GitHub：https://github.com/labring/sealos
- 社区论坛：https://sealos.run/community/
