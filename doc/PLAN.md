# ResearchRadar 实施计划

制定日期：2026-09-10。

依据：[AGENTS.md](../AGENTS.md)、[DEVELOPMENT.md](DEVELOPMENT.md)、[TASKS.md](TASKS.md)。

## 1. 当前状态与目标

当前项目仅包含上述三份规范文档，尚无应用代码、项目依赖配置或测试；当前目录不是 Git 仓库。

本次交付仅为实施计划，不启动代码开发。后续按 TASKS.md 的阶段逐项实施，每阶段完成验收后结束当前任务，不自动进入下一阶段。

MVP 的用户场景：用户查询 Agent / RAG / Reasoning 最近 7 天的研究，能够看到 New / Hot 榜、论文贡献、相对已有工作的变化和可追溯的原文证据。

MVP 完成边界为 TASKS.md 的 Phase 0–11。ResearchEvent、Timeline、个性化、Digest 和 Trend 属于后续阶段；不纳入首个版本。注意 DEVELOPMENT.md 的产品“Phase 2”和 TASKS.md 的开发“Phase 2”含义不同，本计划的阶段编号均引用 TASKS.md。

## 2. 架构与实施约束

- 使用模块化单体，采用 Python 3.12+、FastAPI、Pydantic v2、SQLAlchemy 2、PostgreSQL、Alembic、asyncio 和 httpx。
- API 调用应用服务，服务编排领域逻辑与 Repository / Provider / Collector；领域规则不导入外部 SDK，路由不包含 SQL。
- 外部数据源通过独立适配器接入；Semantic Scholar 使用 EnrichmentProvider，不承担主采集职责。
- 所有重要 LLM 输出经过 Pydantic 和业务校验后持久化；测试使用 FakeLLMProvider。
- 排序由确定性代码计算，权重可配置；缺失指标保持缺失并按可用权重归一化。
- 使用迁移、唯一约束和 upsert 保证持久化与幂等；禁止启动应用时隐式修改生产表结构。
- 先元数据过滤与排序，再低成本筛选，仅对入选论文做全文分析。
- 论文、PDF 和网页内容均作为不可信数据处理；生成结论保留证据、输入哈希、provider、model 和 prompt_version。
- 不预先引入微服务、Kafka、Kubernetes、复杂 Agent 框架、Redis 或分布式任务队列。

## 3. 规范中的依赖补齐

以下是实施安排，不代表这些能力已经实现。

| 事项 | 处理计划 |
| --- | --- |
| Phase 4 分类先于 Phase 7 Provider | 在 Phase 4 实现分类所需的最小 LLMProvider Protocol 与 FakeLLMProvider；Phase 7 再接入真实 Provider、用量记录和完整运行能力。Phase 4 完成时明确实际 LLM 分类尚未上线。 |
| Embedding 没有独立任务 | Phase 3 增加最小 EmbeddingProvider 边界与测试替身，验证去重 fallback；Phase 4 可先采用关键词 shortlist。Phase 7 接入真实 embedding 适配器并经迁移启用 pgvector 存储与检索；Phase 10 验收 prior-paper 检索。仅有替身时不宣称语义检索已可生产使用。 |
| 多来源合并需要来源记录 | Phase 1 建立 PaperSourceRecord 与来源唯一约束，作为 Phase 3“1 Canonical Paper + 2 Source Records”的必要前置。Paper 的稳定内部 ID 与可补充的 DOI / arXiv 等外部标识分开。 |
| API 路径写法不一致 | 统一采用 DEVELOPMENT.md 的 `/api/v1` 前缀；TASKS.md 的 `/feed`、`/papers/{id}` 等视为省略前缀的示例。健康检查保留 `/health`。 |
| 摘要字段清单不完全一致 | 采用 DEVELOPMENT.md 的完整 PaperSummary 字段集，包含 why_problem_matters、previous_approaches 和 experiment_setup；字段必须出现，允许缺失信息的字段显式 nullable，不编造内容补齐。 |
| 引用数量与引用增速不同 | MVP 可使用 citation_count，明确记录信号名称与归一化方式；只有具备可比的历史快照后才计算 citation_velocity，不将数量冒充增速。 |
| Job 与持续运行没有独立阶段 | Phase 2–3 建立采集运行状态与可重复执行入口；Phase 11 接入单进程异步 Worker 或调度器，验收定时运行、失败隔离和重跑。 |
| Provenance 不能等到 ResearchEvent | Phase 8 起为摘要和比较保存结构化证据引用；Phase 9 增加章节与文本位置；Phase 12 复用证据模型。 |

## 4. MVP 阶段计划

| 阶段 | 主要交付 | 验收重点 |
| --- | --- | --- |
| Phase 0：Bootstrap | uv / pyproject.toml、必要目录、配置、FastAPI 应用、PostgreSQL 本地配置、Alembic 基础配置、pytest / ruff / mypy、README | `/health` 返回 `{"status":"ok"}`；配置校验和健康检查测试通过；测试、lint、typing 全部通过。 |
| Phase 1：领域与存储 | Paper、Topic、PaperTopic、PaperMetric、PaperSummary、IngestionRun、PaperSourceRecord；Repository；初始迁移 | PostgreSQL 中 create / get / update / list round-trip；来源唯一约束；指标支持缺失值和采样时间；迁移可在空库应用。 |
| Phase 2：采集框架 | RawPaper、PaperCollector、ArxivCollector；HTTP 与 parser 分离；请求超时、重试与采集状态 | XML fixture 正确解析；分页和时间边界；timeout / 429 / 5xx 最多尝试 3 次，指数退避加 jitter；400 / 401 / 403 不盲目重试。 |
| Phase 3：规范化与去重 | 标题与标识标准化、canonical identity、跨来源映射、metadata merge、语义 fallback 边界、幂等入库 | 按 DOI → arXiv ID → 已知映射 → 标准化标题 → embedding fallback 匹配；多来源合为一篇且保留来源；相同批次重跑不重复；并发写入受数据库约束保护。 |
| Phase 4：主题分类 | 可配置固定 taxonomy、关键词候选集、结构化分类、最小 LLMProvider 与 FakeLLMProvider、版本化 prompt | 至少 30 篇 Agent / RAG / Reasoning fixture；非法 slug 和置信度校验；低于 0.60 不自动关联；区分离线流程测试与真实模型效果评估。 |
| Phase 5：排序 | Relevance、Freshness、New、Hot；权重配置、信号归一化、分数解释 | 新且相关的论文 New 靠前；较旧但高热度论文 Hot 靠前；缺失与真实零值不同；全部信号缺失时返回不可评分状态；同分稳定排序。 |
| Phase 6：多源与补充指标 | HuggingFaceCollector、OpenReviewCollector、SemanticScholarEnrichmentProvider、指标快照 | 每个适配器独立 fixture 测试；跨源去重；HF upvotes、引用数量、OpenReview rating 可保存；一个来源失败仍持久化其他来源结果。 |
| Phase 7：真实 Provider | 至少一个真实 LLMProvider、真实 EmbeddingProvider、pgvector 检索；timeout、retry、usage、模型与 prompt 元数据 | 业务模块无 SDK 直接调用；结构化响应和失败分类测试；token 与可获得的成本信息可记录；凭证不进入日志；测试不调用付费 API。 |
| Phase 8：结构化摘要 | 摘要筛选与预算限制、基于 title / abstract 的 PaperSummary、证据与生成记录、版本化 prompt | 缺少必要字段或证据不合法时拒绝入库；标记 abstract-only 输入范围；信息不足时显式说明；相同输入与生成版本不重复处理。 |
| Phase 9：全文分析 | PDF 获取、解析、FullTextDocument、section extraction、按章节分块、入选论文全文摘要 | PDF fixture 保留章节与文本定位；覆盖损坏 PDF、无可提取文本、下载失败、过大文件；控制输入长度；全文失败时保留并标明摘要级结果。 |
| Phase 10：已有工作比较 | 同主题且早于目标论文的候选检索、最多 top 5、PaperComparison、证据链接和 Repository | 排除目标自身与未来论文；输出差异、继承、创新与权衡；无 prior papers 时返回信息不足状态；论文详情可返回 summary / comparison。 |
| Phase 11：Feed 与闭环 | New / Hot Feed、Topic 查询、论文详情、手动摘要触发、运行入口与调度、公开 API 文档 | 完整跑通 collect → dedup → classify → rank → screen → summary / comparison → feed；支持 topic 和时间窗口筛选；重复执行无重复数据；部分来源失败时仍可用。 |

各阶段所需的新表或字段均随所属阶段追加迁移，不在 Phase 1 提前建立后续所有业务表。Semantic embedding 自动合并采用 DEVELOPMENT.md 的建议阈值作为初始配置，并用重复与非重复样本验证；存在强标识冲突时不因语义相似而强制合并。

## 5. MVP 的公开接口范围

- `GET /health`
- `GET /api/v1/feed?type=new|hot&topic=agent&limit=20`，补充并文档化查询时间窗口与分页参数。
- `GET /api/v1/papers/{paper_id}`
- `POST /api/v1/papers/{paper_id}/summary`
- `GET /api/v1/topics`
- `GET /api/v1/topics/{slug}`
- `GET /api/v1/topics/{slug}/papers`

未生成的 summary / comparison 显式返回空值或状态；手动摘要触发使用异步执行状态，并对重复请求保持幂等。具体请求和响应 schema 在对应 API 阶段确定并写入 OpenAPI 与 README。

## 6. 测试与交付门槛

每阶段必须满足：实现与对应测试存在，测试通过，lint 通过，类型检查通过，公开接口有文档，无无关改动，失败路径已覆盖。

默认检查命令：

```bash
uv run pytest
uv run ruff check .
uv run mypy app
```

测试分层：

- 单元测试：标识标准化、去重规则、缺失指标归一化、taxonomy、结构化输出与证据校验。
- 适配器测试：外部 HTTP 全部使用 mock / fixture，覆盖分页、超时、限流、认证错误和畸形响应。
- 数据库集成测试：独立测试 PostgreSQL，验证迁移、事务、唯一约束、upsert 和 pgvector；数据库就绪后执行，不以静默跳过替代验收。
- LLM 流程测试：FakeLLMProvider；注入不符合 schema、无证据和带恶意指令的论文内容，验证校验与数据边界。该测试不等同于真实模型质量保证。
- 端到端测试：固定时间与固定样本，验证榜单、来源追溯、重复运行和部分失败恢复。

MVP 最终验收用例：Agent 最近 7 天，返回可解释的 New / Hot Top 论文，入选论文有结构化摘要、What Changed 和相关 prior papers；证据能够定位回输入来源；无足够证据时不编造比较；同一时间窗口重跑不生成重复记录。

真实服务的接口兼容性和真实模型效果在接入阶段基于官方文档与独立评估验证；离线测试通过不代表已验证实时数据质量。

## 7. MVP 之后的顺序

以下仅保留路线，不属于当前实现范围：

| 阶段 | 目标 | 关键约束 |
| --- | --- | --- |
| Phase 12 | ResearchEvent | 只为有意义的变化生成事件；必须有可验证证据，允许不生成事件。 |
| Phase 13 | Topic Timeline | 从 ResearchEvent 排序、聚合并保留来源与置信度；不凭模型知识编造历史。 |
| Phase 14–15 | Research Memory 与 Personalized Feed | 记录兴趣、反馈与阅读历史；至少 5% 推荐用于探索。 |
| Phase 16 | Daily / Weekly Digest | 按时间窗口聚合、去重和综合变化，利用历史避免重复。 |
| Phase 17 | Trend Engine | 基于论文、历史指标快照和事件计算趋势；处理缺失数据和采集覆盖变化。 |
| Phase 18 | 可选 Idea Discovery | 在前述能力稳定并有明确需求后单独规划。 |

## 8. 下一项任务：Phase 0

建议下一次仅执行 Task 0.1：

1. 检查本地 Python、uv 和 PostgreSQL / 容器运行环境，确定可复现的开发与测试命令。
2. 新建 pyproject.toml、锁文件、配置示例、忽略规则与 README；按规范建立必要包目录，不填充未来业务实现。
3. 创建 FastAPI 应用工厂与 `/health`；配置通过 Pydantic Settings 读取，不提交密钥。
4. 配置 SQLAlchemy 数据库访问基础、Alembic 和本地 PostgreSQL；领域表留到 Phase 1。
5. 添加健康检查、配置与应用启动相关测试；运行 pytest、ruff、mypy。
6. 按 Changed / Tests / Design decisions / Known limitations / Next task 汇报，以此结束任务。

首个任务不接入真实论文源、不调用付费模型、不实现排名或摘要。当前还不是 Git 仓库，后续如需要按 TASKS.md 建议记录提交，先初始化版本管理；不在本次计划任务中创建提交。
