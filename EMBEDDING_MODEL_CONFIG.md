# Embedding 模型配置说明

## 模型切换

系统已从 **DashScope text-embedding-v3** 切换到 **BGE-large-zh-v1.5**（中文优化）。

---

## 模型对比

| 特性 | BGE-large-zh-v1.5 | DashScope text-embedding-v3 |
|------|-------------------|----------------------------|
| **运行方式** | 本地运行 | API 调用 |
| **向量维度** | 1024 | 1536 |
| **中文优化** | 是 | 是 |
| **API Key** | 不需要 | 需要 |
| **首次使用** | 自动下载模型 (~1.3GB) | 无需下载 |
| **响应速度** | 快（本地） | 依赖网络 |
| **成本** | 免费 | 按调用收费 |

---

## 自动回退机制

系统配置了智能回退机制：

1. **优先使用** BGE-large-zh-v1.5（本地模型）
2. **如果失败** 自动切换到 DashScope API（需配置 `DASHSCOPE_API_KEY`）

---

## 使用方式

### 方案一：使用本地 BGE 模型（推荐）

```bash
# 1. 确保已安装 FlagEmbedding
pip install FlagEmbedding

# 2. 直接运行即可（模型自动下载）
python ingest_enhanced.py

# 3. 启动应用
streamlit run app.py
```

**首次运行** 会自动从镜像源下载模型（约 1.3GB），后续使用无需下载。

### 方案二：使用 DashScope API（备选）

如果本地模型下载失败或运行有问题，可使用 DashScope API：

```bash
# 1. 配置 API Key
export DASHSCOPE_API_KEY=sk-xxx

# 2. 修改 config.py 中的配置
EMBEDDING_MODEL = "text-embedding-v3"
```

---

## 网络问题解决方案

### 中国国内用户

系统已自动配置国内镜像源：

```python
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
```

如果仍然下载失败，可尝试：

1. **手动下载模型** 到本地缓存目录
2. **使用代理** 访问 Hugging Face
3. **切换到 DashScope API**

### 手动下载模型

```bash
# 使用 huggingface-cli 下载
huggingface-cli download BAAI/bge-large-zh-v1.5 \
  --local-dir ~/.cache/huggingface/hub/models--BAAI--bge-large-zh-v1.5
```

---

## 配置选项

### config.py

```python
@dataclass
class DashScopeConfig:
    embedding_model: str = "bge-large-zh-v1.5"  # 或 "text-embedding-v3"
```

### 环境变量

```bash
# 可选：自定义 Embedding 模型
export EMBEDDING_MODEL=bge-large-zh-v1.5

# 备选：DashScope API Key
export DASHSCOPE_API_KEY=sk-xxx
```

---

## 验证安装

```bash
python -c "
import os
os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'

from FlagEmbedding import FlagModel
model = FlagModel('BAAI/bge-large-zh-v1.5')
result = model.encode('测试中文')
print(f'向量维度：{result.shape}')
"
```

---

## 故障排查

### 问题 1: 模型下载超时

**现象**: `ReadTimeoutError` 或 `ConnectionError`

**解决方案**:
1. 检查网络连接
2. 确保设置了 `HF_ENDPOINT=https://hf-mirror.com`
3. 使用代理或切换到 DashScope API

### 问题 2: 磁盘空间不足

**现象**: 模型下载失败

**解决方案**:
- BGE-large-zh-v1.5 需要约 1.3GB 空间
- 清理磁盘或缓存到其他位置

### 问题 3: Windows 开发者模式

**现象**: 缓存 symlinks 警告

**解决方案**:
- 激活 Windows 开发者模式（推荐）
- 或忽略警告（功能正常，占用更多空间）

---

## 性能优化

### GPU 加速（可选）

如有 NVIDIA 显卡，可安装 CUDA 版本：

```bash
pip install FlagEmbedding[cuda]
```

### 半精度推理

```python
# 修改 use_fp16=True 可减少内存占用
model = FlagModel('BAAI/bge-large-zh-v1.5', use_fp16=True)
```

---

## 参考资源

- [BGE 模型论文](https://arxiv.org/abs/2302.03289)
- [FlagEmbedding GitHub](https://github.com/FlagOpen/FlagEmbedding)
- [Hugging Face 模型页面](https://huggingface.co/BAAI/bge-large-zh-v1.5)
- [国内镜像源](https://hf-mirror.com)
