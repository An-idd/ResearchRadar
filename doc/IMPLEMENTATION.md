# MVP 实施与验收

日期：2026-09-11。范围：Phase 0–11；用户授权使用 Neon PostgreSQL，并使用本地 Codex 实现研究分析。

## Changed

| 阶段 | 落地内容 | 验证 |
| --- | --- | --- |
| 0 | Python 3.12 / uv、FastAPI、Pydantic Settings、ruff、mypy | 健康检查、配置、Windows Uvicorn 事件循环 |
| 1 | Paper、Topic、PaperTopic、PaperMetric、PaperSummary、IngestionRun、来源记录、Repository | Neon 数据库读写和两个版本的 Alembic 迁移 |
| 2 | arXiv Atom parser、分页与窗口、HTTP 重试边界 | XML fixture、超时/429/5xx 与 400/401/403 分类 |
| 3 | DOI/arXiv/来源映射/标题/向量去重、元数据合并 | 多来源保留、并发重复写入、强标识冲突与 embedding fallback |
| 4 | JSON taxonomy、关键词候选、结构化分类 | 30 篇 fixture、未知 slug、0.60 阈值；真实 Codex 分类 |
| 5 | New / Hot、权重归一化、可解释信号 | 缺失与零值、无信号、热度/时间排序 |
| 6 | HF、OpenReview、Semantic Scholar enrichment | HTTP fixtures；真实 arXiv/HF 成功；OpenReview 403 被隔离 |
| 7 | Codex CLI / OpenAI 兼容 Provider、Fake Provider、本地 FastEmbed、pgvector | Codex 真实 JSON 输出与 token 记录；本地真实 384 维向量 |
| 8 | 筛选、预算限制、结构化摘要、证据和生成缓存 | 缺字段/伪造引用拒绝持久化、重复任务复用缓存 |
| 9 | 受限 PDF 下载、章节/页码/偏移、分块、摘要回退 | PDF fixture、损坏/空白/过大 PDF、重定向安全；真实超大 PDF 正确回退 |
| 10 | 同主题更早论文、pgvector top 5、结构化比较 | 排除自身/未来论文；真实 Codex 比较带双侧引用 |
| 11 | Feed / Paper / Topic / Job API、持久化 worker、周期采集 | Neon 全链路测试、任务恢复、API HTTP 冒烟验证 |

代码按模块化单体组织。配置文件与接口用法见 [README](../README.md)，数据库环境见 [NEON](NEON.md)。没有修改生产数据库，没有自动提交 Git，没有实现 Phase 12+。

## Tests

- 免费测试全部使用 fixture、MockTransport、FakeLLMProvider；集成测试实际连接 Neon `mvp-test`，不会回退 SQLite 或静默跳过数据库验证。
- 最终检查通过：`uv run pytest`（66 passed，208.83 秒）、`uv run ruff check .`、`uv run mypy app`（39 个源文件）、`uv run alembic check`（无 schema drift）。
- 已在专用测试分支完成 `alembic downgrade base` → `upgrade head` → `check`；两次迁移无 schema drift。
- 真实验证单独执行，不属于自动化测试：Codex 登录、结构化输出、本地 embedding、arXiv/HF 采集、HTTP API 和真实论文摘要/比较。
- 本地 HTTP 验证：`/health`、`/docs`、Topics、Agent New/Hot Feed 均返回 200，摘要请求返回 202，持久化任务完成后详情返回 summary / comparison。

开发库验收时保存 22 篇真实论文、1 份真实摘要和 1 份真实比较；原生产库 public schema 仍无业务表。API 已在本机 `127.0.0.1:8000` 启动。当前未常驻采集 worker；可按 README 运行 `worker`，或使用 `run-once --jobs-only` 处理手动任务。

真实案例：开发库的 `MindTopo: Can Foundation Models Reason in Topological Space?`（arXiv `2609.11900v1`）完成了摘要和比较，任务 `05bdb10a-4489-4719-8419-0618f3f9c279` 成功。摘要包含 17 条证据，比较包含 6 条证据。PDF 超出 15 MB 限制，结果明确标记 `abstract-only`。该案例只证明端到端调用和证据定位成功，不是模型质量评估结论。

## Design decisions

- 数据库使用 Neon `development`；迁移与集成测试用独立 `mvp-test`（2026-09-18 到期），原 `production` 保持原状。
- SQLAlchemy 使用 pooled URL；Alembic 和 worker 会话锁使用 direct URL；不在应用启动执行 DDL。
- Codex 经独立 Provider 调用，采用已有登录及明确模型配置，隔离目录、只读沙箱、关闭 shell/搜索/应用/插件，结构化输出先校验后保存。调用仍消耗远程账号额度。
- FastEmbed 在本机 CPU 生成向量；Windows 锁定已验证可用的 ONNX Runtime 1.20.1。
- 不引入 Redis、分布式队列或额外 Agent 框架。一个 worker 通过数据库锁协调，失败状态持久化；来源和每条论文独立容错。
- 指标快照记录实际采样时间；重复访问来源可以生成新采样，但论文、来源身份和相同输入版本的分析不会重复。

## Known limitations

- OpenReview 当前返回 `ChallengeRequiredError`（403），需要官方浏览器验证或可用的合法访问环境；未绕过验证。其离线适配器测试通过，真实采集仍受此限制。
- Semantic Scholar 有匿名限流风险；适配器有 mock 验证。真实模型的准确率、摘要完整性、检索阈值需更大样本评估；未声称通过质量基准。
- 自动验证能检查引用存在、字段覆盖与来源日期，不能证明每个引文在语义上充分支持结论。
- 全文暂不支持 OCR、加密 PDF、100 页以上或 15 MB 以上 PDF；这些情况保留 abstract-only 分析。
- 所有查询和比较仅覆盖已收录论文；采集按每源条数上限运行，关键词 shortlist 可能漏召回；相似度 0.90–自动合并阈值之间的候选在来源 metadata 中标记 potential_duplicates，保留独立论文，目前没有人工审核界面。
- 已存在的两个 canonical paper 出现需要跨记录合并的标识桥接时，保守报告冲突，留待人工核对，避免破坏历史来源和分析。
- 当前 Feed 在选定时间窗口内由 Python 排序，元数据合并串行化，适用于 MVP 数据量；后续有性能证据再优化。
- 默认 API 面向本机单用户；跨机器绑定需 ADMIN_TOKEN。任务处于 queued 时需要运行 worker。模型返回后、入库前崩溃仍可能重复消耗一次调用。
- OpenAI 兼容 HTTP Provider 只有 mock 测试，未调用付费 API；Codex 未报告货币成本时记录 null。

## Next task

优先处理 OpenReview 的正常访问、积累更长时间窗口的同主题 prior papers，并抽样评估 Codex 研究结论与语义去重阈值。ResearchEvent / Timeline 等下一阶段功能另行确定范围。
