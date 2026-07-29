# Marginalia RAG

书隅读思——一个带有无剧透 AI 助手的小说电子书阅读器。

用户上传小说后，可以直接在网页中阅读，并询问人物、剧情和此前发生的事件。系统只检索用户实际读过的内容，回答同时提供可跳转的原文出处。

## MVP 范围

项目分成两个部分：

### 电子书阅读器

- 上传 EPUB 小说，兼容 UTF-8/GB18030 TXT
- 读取 EPUB metadata、spine 与 TOC
- 自动识别目录和章节
- 书架与小说管理
- 阅读页面与章节目录
- 主题、字号和行高设置
- 自动保存章节与段落阅读位置

### LangChain RAG

- 小说原文切块
- PostgreSQL + pgvector Dense 检索
- BM25 关键词检索
- Hybrid 混合检索
- 按阅读位置过滤检索结果
- 基于证据回答，并提供原文引用
- 证据不足时拒绝回答

## 无剧透边界

每个 Chunk 保存：

```text
novel_id
chapter_number
start_offset
end_offset
```

检索结果必须满足：

```text
chunk.chapter_number < current_chapter

或

chunk.chapter_number == current_chapter
且 chunk.end_offset <= current_offset
```

这个约束必须在数据库检索层执行，不能只依赖 Prompt。

## 技术栈

- Frontend：React、TypeScript、Vite
- Backend：FastAPI、SQLAlchemy、Alembic
- Database：PostgreSQL 16、pgvector
- RAG：LangChain
- Local infrastructure：Docker Compose

## 当前骨架

```text
.
├── backend/
│   ├── migrations/        # Alembic 与初始 pgvector schema
│   ├── src/
│   │   ├── api/           # FastAPI 路由
│   │   ├── core/          # 环境配置
│   │   └── db/            # SQLAlchemy 模型与会话
│   └── tests/
├── frontend/
│   └── src/               # React 应用
├── compose.yaml           # PostgreSQL + pgvector
└── .env.example
```

当前已定义 `novels`、`chapters`、`reading_progress` 和 `chunks` 数据表。

## Ollama Embedding 与检索

默认使用本机 Ollama 的 `bge-m3:latest`（1024 维）。向量保存在独立的
`chunk_embeddings` 表中，并记录模型名和维度，因此同一 Chunk 可以扩展到多个
Embedding 模型。

每次索引都会创建独立的 `index_profiles` 记录，不覆盖旧 Chunk。前端阅读器的
“索引”面板可以选择段落/固定窗口预设、建立新方案并切换当前方案。检索默认使用
当前启用方案，也可以通过 `profile_id` 显式查询历史方案。

索引通过 FastAPI 后台任务分批执行。`POST /api/v1/rag/index` 会立即返回状态为
`queued` 的 Profile；前端每秒读取 `processed_chunks / chunk_count` 并显示进度。
任务依次进入 `chunking`、`embedding`、`ready`，完成后自动启用；失败时保留
`failed` Profile 和 `error_message`，原 Active Profile 不受影响。

“预览当前章”调用 `/api/v1/rag/preview`，只计算 Chunk 边界，不写数据库，也不
调用 Embedding 模型。阅读器的“问书”面板调用 `/api/v1/rag/ask`：先从当前索引
检索已读范围内的 Top-K 原文，再由 Ollama `qwen3:4B` 生成带 `[1]`、`[2]` 证据
编号的回答。接口会剥离 Qwen 的内部思维链，只向前端返回最终答案。

先建立索引：

```powershell
$body = @{
  novel_id = "替换为小说 UUID"
  model = "bge-m3:latest"
  chapter_limit = 3
  target_size = 700
  max_size = 900
  overlap = 100
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/rag/index `
  -ContentType "application/json" `
  -Body $body
```

再进行向量检索：

```powershell
$body = @{
  novel_id = "替换为小说 UUID"
  query = "这本书的作者是谁？"
  model = "bge-m3:latest"
  top_k = 5
  max_chapter = 3
  max_offset = 2147483647
} | ConvertTo-Json

Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/rag/search `
  -ContentType "application/json; charset=utf-8" `
  -Body ([System.Text.Encoding]::UTF8.GetBytes($body))
```

生产阅读流程可以省略 `max_chapter` 和 `max_offset`，接口会读取
`reading_progress`，并在 PostgreSQL 查询层排除尚未读到的 Chunk。

M1 已实现：

- EPUB 2/3 上传和 ZIP 安全检查；
- EPUB metadata、spine、Navigation/NCX 目录解析；
- XHTML 正文清洗与章节源定位；
- UTF-8 与 GB18030 TXT 上传；
- EPUB 50 MB、TXT 20 MB 限制和重复内容检测；
- 常见中文章节标题识别；
- 小说、章节正文和精确字符偏移入库；
- 书架列表和章节查询 API；
- 前端上传表单、处理反馈和书架展示。

M2 已实现：

- 点击书架进入阅读页面；
- 章节目录、上一章和下一章；
- 纸白、护眼和夜间主题；
- 字号和行高设置；
- 当前显示位置自动保存；
- 最远已读位置只前进、不因回看倒退；
- 重新打开小说后恢复上次章节和滚动位置。

## LangChain 聊天模型

`POST /api/v1/rag/ask` 的生成阶段通过 LangChain 统一调用聊天模型。向量检索和
无剧透范围过滤仍由 PostgreSQL + pgvector 完成，因此更换聊天模型不需要重新切块或
生成 Embedding。

默认使用本机 Ollama：

```dotenv
LLM_PROVIDER=ollama
LLM_MODEL=qwen3:4B
LLM_BASE_URL=http://127.0.0.1:11434
LLM_API_KEY=
```

切换到 OpenAI 时，设置 `LLM_PROVIDER=openai`、模型名和 API Key；对于实现标准
OpenAI Chat Completions 接口的其他服务，使用 `LLM_PROVIDER=openai_compatible`
并同时配置 `LLM_BASE_URL`。API Key 只保存在后端环境变量中，不会发送到前端。

阅读器的“问书”面板支持在本地 Ollama、云端 Qwen 和 DeepSeek 之间切换。云端模型
需要在 `.env` 中配置对应密钥，未配置的选项会保留显示但不可选择：

```dotenv
QWEN_API_KEY=
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_CHAT_MODEL=qwen-plus

DEEPSEEK_API_KEY=
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_CHAT_MODEL=deepseek-v4-flash
```

修改 `.env` 后需要重启后端。前端通过 `/api/v1/rag/chat-models` 获取可用模型，
不会读取或接收 API Key。

## 本地启动

先复制环境配置：

```bash
cp .env.example .env
```

启动 PostgreSQL：

```bash
docker compose up -d postgres
```

Reader 数据库使用宿主机端口 `5433`，避免与本机其他 PostgreSQL 实例冲突。

创建并激活 Conda 环境：

```bash
conda env create -f environment.yml
conda activate reader
```

依赖版本统一记录在 `backend/requirements.txt`。环境已存在时可执行：

```bash
python -m pip install -r backend/requirements.txt
```

初始化数据库：

```bash
cd backend
alembic upgrade head
```

启动后端：

```bash
uvicorn src.api.main:app --reload
```

另开终端启动前端：

```bash
cd frontend
npm install
npm run dev
```

- Web：http://localhost:5173
- API：http://localhost:8000
- API 文档：http://localhost:8000/docs
- 健康检查：http://localhost:8000/health

## 开发顺序

1. TXT 上传、编码检查与章节拆分
2. 书架、阅读页与进度保存
3. Chunk 与 Embedding 入库
4. 已读范围过滤的 Dense 检索
5. BM25 与 Hybrid 检索
6. LangChain 问答、拒答和引用跳转

## 隐私与版权

- 不提交小说原文、生成的 Chunk、Embedding 或 API Key。
- 云端模型模式下，应明确提示哪些文本会发送至第三方 API。
- 公开演示优先使用公版小说。
- 用户应确保拥有上传和处理相关文本的权利。
