# RAG 系统新增功能说明

## 功能概述

本次优化新增了三大核心功能，提升 RAG 系统的准确性和用户体验：

1. **反思链路 (Reasoning Judge)** - 让大模型在回答前先判断文档是否有答案
2. **反馈收集 (Feedback Collector)** - 收集用户对 AI 回答的点赞/踩反馈
3. **多轮对话管理 (Conversation Manager)** - 支持上下文理解的追问

---

## 1. 反思链路 (Reasoning Judge)

### 功能目的
让大模型在回答前先进行判断："提供的文档里是否有答案？"
- 如果文档中有答案 → 正常回答
- 如果文档中没有答案 → 直接告知用户，避免幻觉

### 工作流程
```
用户提问
    ↓
检索相关文档
    ↓
【新增】LLM 判断文档是否有答案
    ↓
根据判断结果生成响应
    ↓
显示答案 + 思考过程
```

### 判断结果类型
| 结果类型 | 说明 | 响应方式 |
|----------|------|----------|
| `answer_found` | 文档中明确包含答案 | 正常回答 |
| `partial_found` | 文档包含部分信息 | 回答并说明局限性 |
| `no_answer` | 文档中无相关信息 | 直接告知用户 |
| `uncertain` | 无法确定 | 谨慎回答 |

### 用户界面
- 默认显示最终答案
- 提供"🤔 查看思考过程"按钮，展开可查看：
  - 分析结果（✅/⚠️/❌/❓）
  - 置信度
  - 分析过程
  - 参考片段数

### 配置开关
在聊天界面底部"⚙️ 功能设置"中可启用/禁用反思链路。

---

## 2. 反馈收集 (Feedback Collector)

### 功能目的
收集员工对 AI 回答的点赞/踩反馈，被"踩"的问题自动汇总成报告，提醒 HR 补充或更新文档。

### 用户操作
每个 AI 回答下方显示反馈按钮：
- **👍 有用** - 一键点赞
- **👎 无用** - 点击后弹出评论输入框（可选填写）

### 数据处理
- 所有反馈保存到 `./feedback_logs/feedback_logs.json`
- 支持按会话 ID 追踪
- 记录引用来源，便于定位问题文档

### 自动生成报告
系统自动生成负面反馈汇总报告：
- 文件位置：`./feedback_logs/downvote_report.md`
- 报告内容：
  - 问题汇总（按被踩次数排序）
  - AI 回答示例
  - 参考来源
  - 用户评论
  - 反馈时间线
  - 处理建议

### 统计信息
```python
{
    "total_feedbacks": 总反馈数，
    "upvotes_30d": 30 天内点赞数，
    "downvotes_30d": 30 天内点踩数，
    "satisfaction_rate": 满意度，
    "downvote_categories": 负面反馈分类
}
```

### 导出功能
支持导出 CSV 格式：`./feedback_logs/feedback_export.csv`

---

## 3. 多轮对话管理 (Conversation Manager)

### 功能目的
支持追问，系统需理解上下文中省略的信息。

**示例：**
```
用户：出差补助多少？
AI: 根据文档，一线城市每天 200 元，其他城市每天 150 元。
用户：那上海呢？  ← 系统理解这是问"上海的出差补助标准"
AI: 上海属于一线城市，出差补助标准为每天 200 元。
```

### 核心功能

#### 1. 指代消解 (Coreference Resolution)
识别并补全查询中的指代词和省略信息：
- "那上海呢？" → "上海的出差补助标准是什么？"
- "这个流程怎么走？" → "[上文提及的流程] 怎么走？"

#### 2. 上下文窗口
- 默认记住最近 **5 轮** 对话
- 自动提取已提及的实体：
  - 地点（北京、上海等）
  - 话题（出差、报销、请假等）
  - 部门（人力、财务、行政等）
  - 时间参考（今天、本周、本月等）

#### 3. 查询增强
短查询自动补充话题上下文：
```
已提及话题：出差补助
用户输入："广州呢？"
增强后："关于出差补助：广州的补助标准是什么？"
```

### 会话管理
- 每个会话有唯一 ID（显示在功能设置中）
- 点击"🗑️ 清空对话历史"可开始新会话
- 会话 ID 变更自动清空上下文

---

## 技术实现

### 文件结构
```
├── reasoning_judge.py       # 反思链路模块
├── feedback_collector.py    # 反馈收集模块
├── conversation_manager.py  # 多轮对话模块
├── app.py                   # Streamlit 界面（已集成新功能）
├── test_new_features.py     # 测试脚本
└── feedback_logs/           # 反馈数据目录（自动生成）
```

### 依赖要求
所有功能使用现有依赖，无需额外安装：
- `llama-index-llms-dashscope` - LLM 调用
- `chromadb` - 向量数据库
- `streamlit` - Web 界面

### API 使用

#### 反思链路
```python
from reasoning_judge import get_reasoning_judge

judge = get_reasoning_judge(model="qwen-plus")
judgment = judge.judge(query, context)
final_response, thinking = judge.generate_response(
    query, judgment, context, original_answer
)
```

#### 反馈收集
```python
from feedback_collector import get_feedback_collector

collector = get_feedback_collector()
collector.add_feedback(
    question="问题",
    answer="回答",
    feedback_type="upvote",  # 或 "downvote"
    citations=[...],
    user_comment="评论（可选）"
)
```

#### 多轮对话
```python
from conversation_manager import get_conversation_manager

manager = get_conversation_manager(max_turns=5)
resolved_query = manager.resolve_coreference(
    "那上海呢？",
    session_id="会话 ID"
)
```

---

## 使用说明

### 启动应用
```bash
# 确保设置 API Key
export DASHSCOPE_API_KEY="sk-xxx"

# 启动 Streamlit 应用
streamlit run app.py
```

### 功能开关
在聊天界面底部"⚙️ 功能设置"中：
- **启用反思链路** - 切换是否显示思考过程
- **清空对话历史** - 开始新会话
- **会话 ID** - 当前会话标识

### 反馈查看
```bash
# 查看负面反馈报告
cat feedback_logs/downvote_report.md

# 导出 CSV
# 在代码中调用 collector.export_to_csv()
```

---

## 测试验证

运行测试脚本验证所有功能：
```bash
python test_new_features.py
```

测试内容：
1. 反思链路 - 判断文档是否有答案
2. 反馈收集 - 添加点赞/踩反馈，生成报告
3. 多轮对话 - 指代消解，上下文增强

---

## 后续优化建议

1. **反思链路**
   - 优化判断 Prompt，提高准确性
   - 添加判断结果的历史缓存

2. **反馈收集**
   - 集成飞书/钉钉通知，实时推送负面反馈
   - 添加反馈审核流程

3. **多轮对话**
   - 使用专用 NER 模型提取实体
   - 支持更长期的对话记忆（可配置）

---

## 版本信息
- 创建时间：2026-03-28
- 版本：v1.1.0
- 作者：AI Assistant
