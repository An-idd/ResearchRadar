# ResearchRadar

基于 **Neon PostgreSQL + pgvector、本地 Codex CLI、本地 CPU embedding** 的研究情报 MVP。
采集 arXiv、Hugging Face Papers、OpenReview，补充 Semantic Scholar 指标；提供 New / Hot Feed、主题过滤、结构化摘要、What Changed、已有工作比较及原文证据。

后端范围是 [PLAN](doc/PLAN.md) 的 Phase 0–11，现已增加 [Frontend MVP](doc/FRONTEND.md)：论文列表、详情与证据、主题页及分析任务。ResearchEvent、Timeline、个性化、Digest 和趋势属于后续阶段。

## Web 页面

先启动下方的 FastAPI，再另开终端：

```powershell
cd frontend
npm ci
npm run dev
```

打开 <http://127.0.0.1:5173>，可浏览 New / Hot、按主题和日期筛选、阅读摘要及前作比较、展开原文证据。点击生成分析前，在仓库根目录运行 `uv run python -m app.cli worker --jobs-only`；没有 worker 时任务会保持排队。

前端构建、测试、令牌配置与 API 契约更新方式见 [前端开发文档](doc/FRONTEND.md)。

## 启动

需要 Python 3.12、uv、已登录的 Codex CLI，以及 Neon 项目的开发、测试分支。

```powershell
uv sync --locked
neon env pull --project-id square-fog-91407295 --branch development --file .env.development
neon env pull --project-id square-fog-91407295 --branch mvp-test --file .env.test
codex login status
uv run alembic upgrade head
uv run python -m app.cli serve
```

打开 <http://127.0.0.1:8000/docs>。`/health` 仅检查进程存活；应用不会在启动时建表。Windows 请使用上述 CLI 入口，它为 psycopg 配置 Selector 事件循环。

另开一个终端运行采集和分析：

```powershell
# 完成一轮采集、分类、指标补充、排序、摘要/比较后退出
uv run python -m app.cli run-once --days 7

# 持续运行：每 4 小时采集，处理数据库中的摘要任务
uv run python -m app.cli worker --days 7

# 只处理 API 创建的任务，不自动采集
uv run python -m app.cli worker --jobs-only
```

同一个数据库只允许一个 worker，通过直连 PostgreSQL advisory lock 保证。任务保存在数据库中，重启 worker 会恢复中断任务。失败任务保留错误类别，可以再次 POST 摘要接口重试；已成功生成的相同输入/版本使用缓存。进程崩溃在模型返回与入库之间时，恢复可能重新消耗一次模型用量。

## 配置

默认读取 `.env.development`，可通过 `RADAR_ENV_FILE` 选择其他文件。环境变量优先。参考 [.env.example](.env.example)，将需要的非数据库设置补入 `.env.development`；不要覆盖 Neon 已生成的连接值。

| 配置 | 默认 / 用途 |
| --- | --- |
| `DATABASE_URL` | Neon pooled URL，应用查询 |
| `DATABASE_URL_UNPOOLED` | Neon direct URL，迁移和 worker 锁 |
| `LLM_PROVIDER` | `codex`；可选 `openai` 兼容接口 |
| `CODEX_MODEL` | 空值使用 CLI 默认；本机开发配置使用已有 Codex 模型 |
| `CODEX_TIMEOUT_SECONDS` | 每次请求 180 秒，超时/限流最多 3 次尝试 |
| `EMBEDDING_MODEL` | `BAAI/bge-small-en-v1.5`，384 维；变更模型需重算，变更维度需迁移 |
| `DEDUP_SIMILARITY_THRESHOLD` | 默认 0.96 自动合并；0.90 到此阈值之间在来源 metadata 中标记 potential_duplicates |
| `CLASSIFICATION_BUDGET` | 每轮采集所有来源合计最多新分类 50 篇；已确认论文和缓存结果不占预算；失败调用占预算 |
| `RETRY_FAILED_ADMISSIONS` | 默认 `false`；修复认证/配置/输出错误后可临时设为 `true`，显式重试这些失败候选 |
| `SUMMARY_BUDGET` | 每轮最多对排名前 5 篇相关论文筛选和分析 |
| `COLLECTOR_LIMIT` | 每个来源每轮最多扫描/返回 200 条；不是全量历史回填 |
| `FULLTEXT_ENABLED` | `true`，仅入选论文下载全文 |
| `MAX_PDF_BYTES` / `MAX_INPUT_CHARS` | 15 MB PDF；单次正文最多 24000 字符（不包含提示词/schema） |
| `OPENREVIEW_VENUE` | `ICLR.cc/2026/Conference`，按会场配置 |
| `SEMANTIC_SCHOLAR_API_KEY` | 可选；匿名访问可能限流 |
| `ADMIN_TOKEN` | 非本机绑定必须配置；POST 使用 Bearer token |

Codex 在隔离临时目录运行，使用只读沙箱、忽略用户配置，禁用 shell、MCP 配置继承、浏览器搜索、应用与插件。通过 stdin 传递研究内容，通过 JSON Schema 与 Pydantic 验证输出。本地 CLI **仍调用远程 Codex 模型服务并消耗账号额度**，并非离线大模型；embedding 在本机 CPU 运行，首次需要下载模型，之后使用 `.cache/embeddings`。

Windows 上 ONNX Runtime 1.30.0 / 1.23.2 在本机导入崩溃；当前锁定已实测可用的 1.20.1。升级时先运行独立进程导入和 embedding 冒烟检查。

使用 OpenAI 兼容接口时设置 `LLM_PROVIDER=openai`、`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`。该路径仅有 mock 协议测试，未使用真实 API 密钥验收。

## API

| 方法与路径 | 行为 |
| --- | --- |
| `GET /health` | `{"status":"ok"}` |
| `GET /api/v1/feed` | 参数 `type=new|hot`、`topic`、`since`、`until`、`limit=1..100`、`offset` |
| `GET /api/v1/papers/{uuid}` | 元数据、来源原始记录、指标快照、摘要、比较、证据与生成元数据 |
| `POST /api/v1/papers/{uuid}/summary` | 202，返回持久化任务；重复请求复用同一 job ID |
| `GET /api/v1/jobs/{uuid}` | 查询 queued/running/succeeded/skipped/failed 状态 |
| `GET /api/v1/topics` | taxonomy |
| `GET /api/v1/topics/{slug}` | 单个主题 |
| `GET /api/v1/topics/{slug}/papers` | 同 Feed 的时间窗口、排序、分页参数 |

时间窗口为带时区 ISO 8601 的 **[since, until)**，默认最近 7 天，最长 365 天；排序时间基准为 `until`。未知资源 404，错误参数 422。新采集论文必须先确认相关主题才入库；榜单再按发表时间和主题筛选，因此榜单总数仍可能小于数据库总数。升级前已有的未分类记录不会被迁移自动删除，仍可通过论文详情访问。响应包含排序信号和有效权重；缺失指标为 null，不冒充 0。MVP 的 citation_count 是数量，不是引用增速。

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/v1/feed?type=new&topic=agent&limit=20'
uv run python -m app.cli feed --type hot --topic rag --days 7
```

完整请求/响应 schema 见 `/docs` 与 `/openapi.json`。摘要尚未生成返回 null；没有同主题、更早的候选论文时，`comparison_status=insufficient-prior-papers`。比较只检索库中已收录、同 embedding 模型的 earlier papers，最多 5 篇，不能代表完整领域综述。可先扩大采集时间窗口积累 prior papers。

## 数据与分析

模块依赖方向：API → 应用服务 → 领域规则 → Repository / Provider / Collector。数据库迁移在 `migrations/`；不得用 `create_all` 替代生产迁移。

去重按 DOI、arXiv ID、来源映射、标准化标题、embedding fallback 顺序；保留所有来源记录。强标识冲突拒绝自动合并并记录失败，需人工核对。无强冲突且余弦相似度 ≥0.96 时语义合并。元数据写入用数据库事务锁串行化，适合 MVP 批量采集。

主题配置在 [taxonomy.json](config/taxonomy.json)，低于 0.60 不自动关联。采集现在先做关键词初筛，再通过 `topic_classifier:v2` 确认中心贡献与 LLM 主题相关；只有至少一个主题达到阈值，才在同一事务中写入论文、来源详情、指标和主题。无关候选不保存标题、摘要、全文或向量；仅在 `paper_admissions` 保存来源 ID、输入/策略哈希、状态等简短审核与缓存记录。

`collect` 和 `run-once` / `worker` 的采集过程都会调用配置的 LLM Provider；`collect` 不再是仅获取元数据的操作。预算不足标记 `deferred`，调用/校验失败标记 `failed`，均不将候选入库。再次采集时自动重试预算延期、超时、429 和 5xx 等暂时故障；认证或输出校验错误需要修复后显式重试。缓存命中不占新分类预算。升级先显式执行 `alembic upgrade head`，再重启 worker；使用本次创建的 `.env` 时设置 `RADAR_ENV_FILE=.env`。状态、返回计数、历史数据范围及重试限制见 [入库筛选说明](doc/ADMISSION.md)。

排序权重、衰减和指标尺度在 [ranking.json](config/ranking.json)。入库后，排名靠前的论文再经低成本筛选后进行全文分析。

每个非空摘要/比较字段必须带证据，引用包含 paper_id、chunk_id 与原文 quote。程序验证引用存在于实际输入，并持久化源文本、页码/偏移、输入 hash、provider/model、prompt 版本和可获得的用量。**引用位置正确不等于语义一定正确**，真实研究结论仍需人工抽样审查。缺失信息使用 null / 空列表。PDF 获取/解析失败回退并标记 abstract-only；不支持 OCR、加密 PDF 或超过 100 页的 PDF。下载仅允许 arxiv.org、export.arxiv.org、openreview.net 的 HTTPS 地址，并逐次验证重定向。

来源级失败不会撤销其他来源已保存的数据；每条元数据失败也单独记录。超时、429、5xx 按指数退避与 jitter 最多尝试 3 次；400、401、403 和 schema 错误不盲目重试。运行状态与计数保存在 `ingestion_runs`，生成用量在 `generations`，事件日志为 JSON。日志不输出密钥、数据库 URL 或完整模型输入。

## 验证

测试配置必须指向专用 `mvp-test` 分支，不能与开发/生产 endpoint 相同。集成测试会清空该分支的业务表；不配置测试库会明确失败。

```powershell
$env:RADAR_ENV_FILE = '.env.test'
uv run alembic upgrade head
Remove-Item Env:RADAR_ENV_FILE
uv run pytest
uv run ruff check .
uv run mypy app
uv run alembic check
```

纯单元测试可用 `uv run pytest -m 'not integration'`。自动化测试中的外部 HTTP 使用 mock，模型使用 FakeLLMProvider，不调用付费 API、不下载 embedding。30 篇分类 fixture 验证候选与输出约束，不代表真实模型准确率。

迁移升级/降级验收仅在 `mvp-test` 执行。详细分支约定见 [NEON.md](doc/NEON.md)，阶段验收见 [IMPLEMENTATION.md](doc/IMPLEMENTATION.md)。
