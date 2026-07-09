一、全格式智能文档引擎（课程资料预处理 + 临时文件即时解析）
1.1 功能描述
系统提供两套文档处理流水线：

课程资料预处理管道：针对用户上传至某一课程的资料，后台异步完成全格式解析、版面分析、语义分块和向量化，构建持久化的课程知识库。
对话临时文件即时解析：针对用户在对话中上传的临时文件，执行轻量级同步解析（无需 OCR 版面分析，可简化），提取纯文本或结构化摘要，提供给当前对话上下文，不进行持久化存储或向量化入库。
1.2 详细功能要求
1.2.1 课程资料预处理（持久化）
子功能	具体实现要求
多格式兼容解析	支持 PDF（电子/扫描）、Word、PPT、Excel、图片、HTML、Markdown、字幕文件等。
高精度 OCR	集成 PaddleOCR/Tesseract；支持中英文混排、数学公式（Mathpix/本地 LatexOCR）、基础手写体。
版面分析	LayoutLM 或 PP-Structure 检测表格、图片、标题等，重建阅读顺序。
表格智能提取	识别有/无线表格，保留行列结构，处理跨页表格，转为结构化格式。
文档结构抽取	自动提取章节标题层级、图/表标题，生成树状目录。
语义分块	以段落/语义单元分割，token 512~1024，重叠 128，保护公式、表格等特殊块。
向量化与索引	嵌入模型生成向量，结合 BM25 建立倒排索引，按课程 ID 隔离存储。
异步处理管线	上传后异步触发，可查询进度，失败自动重试。
1.2.2 对话临时文件即时解析（非持久化）
子功能	具体实现要求
触发场景	用户在对话中通过上传按钮发送文件，Agent 立即分析该文件以回答当前问题。
支持格式	至少支持图片（JPG/PNG）、PDF、Word、PPT、Excel、文本文件；视频/音频可暂不支持或仅提示不支持。
解析策略	调用轻量解析器（如 PyMuPDF、python-docx 等直接提取文本，图片使用 OCR），不执行版面分析和分块，仅提取全文或关键片段作为上下文。若文件较大（>100MB），可截取前若干页或要求用户明确范围。
生命周期	解析结果存储在内存会话上下文中，与当前轮对话绑定。当用户发送新消息清空上下文或结束会话时，临时内容立即销毁，不留痕迹。
不存储原则	原始文件和解析后的文本均不写入磁盘、不存入数据库、不进入向量索引。仅在会话上下文中以加密内存对象存在。
与知识库协作	Agent 回答时，可将临时文件内容与课程知识库检索结果融合，共同作为生成答案的依据。
1.3 预期效果
课程资料：一次上传，持续可用；任意格式、任意质量的资料均被结构化处理，检索准确率 > 98%。
临时文件：用户可在对话中随时扔一张扫描题或文档，Agent 秒级（<3秒）完成解析并融入答案，不留下任何数据残留，完美保护隐私。
无缝融合：Agent 能同时引用课程已学内容和临时提供的补充材料作答，例如："根据您上传的实验报告截图，与课程第三章的理论对比……"   

二、深度 RAG 与多跳推理问答（流式输出）
2.1 功能描述
Agent 在每轮对话中融合课程知识库和临时文件内容，通过混合检索和多跳推理生成答案。答案以流式方式逐步返回给前端，即 LLM 开始生成时，服务端立即将已生成的 token（字符块）推送给客户端，实现打字机效果，降低用户等待感。

2.2 详细功能要求
功能模块	实现细节
流式传输协议	采用 Server-Sent Events (SSE) 或 WebSocket。推荐 SSE（单向数据流、实现简单）。客户端监听事件流，逐片段更新 UI。
LLM 调用适配	调用支持 streaming 的 LLM 接口（如 OpenAI Chat Completion API 设置 stream: true，或本地模型类似机制）。每次 delta 产生新 token 时，立即封装为 data: {"content": "新增文本", "done": false} 格式发送。
累积与显示	前端接收片段后实时拼接到已有回答末尾，不等待完整答案。结束标记 done: true 表示流结束。
引用注入时机	流式输出内容包含纯文本和引用标记（如 [1]、（临时文件））。引用标记与文本一同流式输出，保证引用即时可见。
多跳推理中的流式	若需要多步推理，Agent 可选择：① 通过多个自然段逐步流式输出思考过程和最终答案（推荐），让用户感知推理步骤；② 仅在最终答案阶段流式输出，但需展示类似"正在分析……"的状态提示。
中断支持	用户可随时中断生成（点击"停止"按钮），客户端断开 SSE 连接，后端终止 LLM 请求，已生成内容可保留展示。
Token 计数与速率	控制流式速率约 30~50 tokens/秒，避免过快导致前端渲染抖动，也避免过慢。可根据网络状况动态调整。
降级处理	若 LLM 不支持流式，系统应提供伪流式（分句模拟）或回退到普通阻塞模式。
信息源融合	每次提问时，系统同时从课程知识库检索相关块，并从会话中提取当前有效的临时文件全文（或摘要）；将两类内容拼接为统一上下文送给 LLM。支持用户明确指定"只看临时文件"或"只看课程资料"。
混合检索	针对课程库：向量 + BM25 + 元数据过滤，RRF 融合排序。临时文件内容不参与检索，而是作为固定上下文附加，确保全部可见。
多跳推理	迭代检索时，允许中间推理步骤同时利用检索结果和附加的临时文件内容；若临时文件提供关键数据，可直接作为推理依据。
引用生成	答案中，来自课程库的信息仍需标注引用编号并可索引；来自临时文件的信息标注为"（临时文件）"，不提供跳转，提示用户此为临时内容。
上下文窗口管理	会话上下文包含对话历史 + 临时文件文本。临时文件文本占用较大 token，系统需动态计算可用余量，必要时自动压缩较早的临时文件（如仅保留关键摘要）或提示用户清空内容。
主动澄清	当临时文件模糊或信息不足时，Agent 应请求用户补充说明或上传完整文件。
隐私保护	所有临时数据处理均在本地或受信环境完成；若使用远端模型 API，临时文件内容不存储，采用一次性会话令牌传输，对话记录不留存文件副本。
2.3 预期效果
零等待感知：首 token 输出延迟 < 1 秒，后续内容连续涌现，用户体验流畅。
透明推理：对于复杂问题，用户可看到 Agent 逐步分析、推理，增强可信度。
随时打断：用户可中途停止生成，避免冗长无用输出。
引用即时性：答案中出现的引用编号与正文同步流出，无需等待全篇完成。

三、实施方案

3.1 关键技术选型

| 决策项 | 选择 | 理由 |
|--------|------|------|
| OCR引擎 | PaddleOCR (主) + EasyOCR (降级) | 均纯pip安装，零系统依赖；PaddleOCR中文印刷体95-98%、手写体~82%，自带版面分析(PP-Structure)和表格识别；EasyOCR作为轻量降级备份 |
| 嵌入模型 | sentence-transformers (all-MiniLM-L6-v2) | ~80MB，384维，离线可用，零API成本 |
| 向量存储 | ChromaDB | Python原生，SQLite后端，内置元数据过滤，与现有技术栈一致 |
| BM25 | rank-bm25 | 纯Python，轻量无外部依赖 |
| 异步处理 | ThreadPoolExecutor + SQLite状态追踪 | 无需Redis/Celery，适用于单用户/小团队规模 |
| 流式协议 | SSE (Server-Sent Events) | 单向数据流，Flask原生支持，实现简单 |
| 临时文件加密 | cryptography.fernet.Fernet | 进程级临时密钥，内容仅存内存 |

3.2 新增Python依赖

PyMuPDF==1.23.8           # PDF解析
python-docx==1.1.0        # Word解析
python-pptx==0.6.23       # PPT解析
openpyxl==3.1.2           # Excel解析
Pillow==10.2.0            # 图片处理
markdown==3.5.2           # Markdown解析
beautifulsoup4==4.12.3    # HTML解析
lxml==5.1.0               # 快速HTML/XML解析器
paddlepaddle==3.0.0       # PaddleOCR深度学习框架 (CPU版)
paddleocr==2.9.0          # 中文OCR首选，自带版面分析+表格识别
easyocr==1.7.2            # OCR降级方案（纯pip，CPU友好）
openai==1.12.0            # DeepSeek API流式调用
sentence-transformers==2.5.1  # 本地嵌入模型
tiktoken==0.5.2           # Token计数
chromadb==0.4.24          # 向量数据库
rank-bm25==0.2.2          # BM25检索
cryptography==42.0.0      # 临时文件加密

> 无需系统级依赖：PaddleOCR 和 EasyOCR 均为纯 pip 安装，首次运行时自动下载模型权重（PaddleOCR ~200MB，EasyOCR ~120MB）。

3.3 数据库变更

documents表新增字段：
- processing_status (pending/parsing/ocr/chunking/embedding/indexing/completed/failed)
- processing_progress (0.0~1.0)
- processing_error TEXT
- structured_content TEXT (JSON)
- toc_tree TEXT (JSON)
- page_count INTEGER
- chunk_count INTEGER
- metadata_json TEXT

新增 document_chunks 表：
- id, document_id, course_id, chunk_index, chunk_type, content, token_count, page_start, page_end, heading_path, metadata_json, chroma_id

新增 document_processing_log 表：
- id, document_id, stage, status, message, duration_ms

新增 temp_file_sessions 表：
- id, session_id, conversation_id, file_name, file_type, file_size, destroyed_at (仅元数据，不含文件内容)

3.4 新增配置项 (config.py)

OCR_ENGINE = 'paddleocr'     # 'paddleocr' 或 'easyocr' (自动降级)
CHUNK_SIZE = 512              # 分块token数
CHUNK_OVERLAP = 128           # 分块重叠token数
EMBEDDING_BACKEND = 'local'   # 'local' 或 'api'
EMBEDDING_MODEL = 'all-MiniLM-L6-v2'
STREAMING_ENABLED = True
TOKEN_RATE = 40               # 流式速率 (tokens/秒)
MAX_CONTEXT_TOKENS = 6000
MAX_PROCESSING_WORKERS = 2
PROCESSING_RETRY_COUNT = 3

3.5 新增后端服务模块 (backend/services/)

document_parser.py     — 多格式解析器（PDF/Word/PPT/Excel/图片/HTML/MD/TXT）+ LightweightParser（临时文件轻量解析）
ocr_service.py         — OCR抽象层：PaddleOCREngine (主) + EasyOCREngine (降级)，自动切换
layout_analyzer.py     — 版面分析（PP-Structure为主，PyMuPDF规则为辅）
table_extractor.py     — 表格提取（PP-Structure + Word/PPT原生表格 + 跨页合并）
document_structure.py  — 文档结构提取（标题层级、图表标题、树状目录）
chunking_service.py    — 语义分块（512 tokens, 128 overlap, 保护特殊块）
embedding_service.py   — 嵌入服务（本地sentence-transformers + API备选）
vector_store.py        — ChromaDB封装，按课程ID隔离Collection
bm25_manager.py        — BM25倒排索引，按课程建立，增删自动重建
retrieval_service.py   — 混合检索（向量+BM25 → RRF融合）+ 上下文构建 + 引用编号
async_pipeline.py      — ThreadPoolExecutor异步管线（解析→OCR→分块→嵌入→索引），进度追踪，失败重试
streaming_service.py   — SSE流式生成器（速率控制、中断检测、伪流式降级）
temp_file_service.py   — 临时文件管理（LightweightParser解析、Fernet加密、内存存储、会话销毁）

3.6 修改后端模块

routes/document.py — POST / 上传后异步处理；GET /<id>/processing 进度查询；POST /<id>/reprocess 重新处理；GET /<id>/chunks 查看分块
routes/chat.py     — POST /<conv_id>/messages/stream SSE流式端点；POST /<conv_id>/upload-temp 临时文件上传；POST /<conv_id>/interrupt 中断生成
routes/agent.py    — POST /chat 增强：支持临时文件session_id，走RAG管线
services/ai_service.py — 新增chat_rag()完整RAG管线，保留原chat() mock降级

3.7 前端修改

js/api.js              — streamMessage() SSE流式接收；uploadTempFile() 临时文件；interruptStream() 中断；getDocumentProcessing() 进度轮询
chat.html              — 临时文件上传按钮+预览栏；流式消息展示（打字机效果）；停止按钮；引用渲染（[1]可点击/临时文件徽章）
js/utils.js            — 增强renderMarkdown()：代码块、表格、列表、链接、引用标记
course_detail.html     — 文档上传进度条；处理状态徽章；失败重试按钮
css/style.css          — .streaming-cursor / .citation / .temp-file-bar / .btn-stop / .upload-progress

3.8 实施顺序

阶段1 (基础) → 阶段2 (解析) → 阶段3 (向量) → 阶段4 (管线) → 阶段5 (RAG流式) → 阶段6 (前端) → 阶段7 (打磨)

3.9 关键风险与缓解

| 风险 | 缓解措施 |
|------|---------|
| PaddlePaddle在部分Windows环境安装失败 | 自动降级到EasyOCR，确保基本OCR功能可用 |
| sentence-transformers首次下载80MB模型 | 启动时预热模型，UI显示"初始化中" |
| ChromaDB与SQLite文件锁冲突 | 独立目录存储，ChromaDB使用WAL模式 |
| 大PDF处理耗时 | 进度百分比轮询，可配置最大页数 |
| LLM流式网络中断 | 指数退避重试，降级为非流式 |
| 后台线程孤儿 | atexit处理器join线程池 |

3.10 验证方案

1. 文档处理：上传各类格式（PDF/Word/PPT/Excel/图片/HTML/MD），确认全流程完成
2. OCR：扫描版PDF和中文图片，确认PaddleOCR识别；模拟不可用时EasyOCR接管
3. 混合检索：对比纯向量/纯BM25/混合检索的结果质量
4. 流式输出：前端逐token显示、引用同步出现、停止按钮可用
5. 临时文件：对话中上传文件→Agent引用"(临时文件)"；新对话后不可访问
6. 隐私：临时文件不写磁盘、不入库、不进向量索引
7. 降级：关闭LLM API后回退mock模式
8. 边界：>100MB截断提示；超长对话上下文管理
