# Frontend MVP 开发与验收

2026-09-11：用户授权按前端计划的 6 个阶段逐步实施。本阶段连接现有后端 Phase 0–11，不包含 ResearchEvent、Timeline、登录、多用户、收藏、搜索、个性化或趋势功能。

## 开发阶段

| 阶段 | 实现 | 验收 |
| --- | --- | --- |
| 1 工程和契约 | React / TypeScript / Vite，三个路由，统一 API 请求，OpenAPI 类型生成 | 构建、lint、API 边界测试、后端契约测试 |
| 2 论文列表 | New / Hot、主题筛选、7/30 天及自定义日期、分页、排序依据、空/错误状态 | 日期边界测试、固定时间窗口翻页、浏览器筛选及返回导航 |
| 3 详情与证据 | 结构化分析、前作比较、逐字段引文、上下文、章节和可用页码 | 同 chunk ID 不同 paper ID 正确区分；不渲染研究内容中的 HTML |
| 4 分析任务 | POST 入队、状态轮询、失败重试、令牌输入、刷新恢复、终态刷新详情 | 重复点击、401、网络中断恢复、终态停止、离页取消、刷新后恢复 |
| 5 主题和阅读体验 | 父子主题导航、主题列表复用、移动端折叠、键盘焦点、路由标题 | 手机无横向溢出、键盘跳转、直接访问与刷新页面 |
| 6 联调与交付 | 真实开发库只读联调、静态构建验收、配置和测试文档 | 浏览器流程、前端检查、后端回归、人工截图检查 |

## 结构和设计决策

`frontend/` 是独立 npm 项目，保留仓库根目录既有 Neon 工具依赖。运行时只使用 React、React DOM 和 React Router；请求使用原生 fetch，样式使用普通 CSS、系统字体和本地 SVG 图标。

浏览器 → `/api/v1` → FastAPI → 原有 Service / Repository。数据库 URL、模型凭据和 Neon 配置只存在于后端。前端开发及预览服务器仅绑定 `127.0.0.1`，将 `/api` 代理到 `http://127.0.0.1:8000`。

路由：

- `/`：论文发现，URL 保存 `type / topic / since / until / offset / limit`。
- `/papers/:id`：论文详情、证据及分析任务。
- `/topics/:slug`：主题说明、父子导航及对应榜单。

组件按页面和实际复用点划分：FeedPage、PaperPage、TopicPage、EvidenceList、JobPanel；没有全局状态库或额外后端服务。

## 启动

Node 版本应满足所锁定 Vite 的要求；本机验证版本为 Node 24.18.1。Python 和 Neon 配置按 [README](../README.md) 准备。

```powershell
# 仓库根目录，终端一
uv run python -m app.cli serve

# 终端二
cd frontend
npm ci
npm run dev
```

访问 <http://127.0.0.1:5173>。要处理页面创建的分析任务，在仓库根目录另开终端：

```powershell
uv run python -m app.cli worker --jobs-only
```

如果后端配置了 ADMIN_TOKEN，在详情页“访问令牌（按需）”中输入。令牌仅存在于当前页面内存并通过 Authorization 请求头发送，离开页面会清除；不写入 URL、localStorage、sessionStorage 或 VITE 环境变量。

## API 契约

后端公开响应模型位于 `app/api_models.py`。Feed 使用 `SummaryPreview`（one_sentence、what_changed、scope、generated_at），详情使用完整 `PaperSummary`；`GenerationView` 暴露输入来源，`JobView` 明确五种状态。

类型通过 OpenAPI 生成，禁止手改 `frontend/src/schema.d.ts`。修改公开模型后在仓库根目录执行：

```powershell
uv run python -m scripts.export_openapi
npm --prefix frontend run types:generate
```

导出过程不连接数据库。`tests/test_api_contract.py` 验证已提交 OpenAPI 快照与后端响应契约一致。模型收紧保留原有成功响应的字段和 JSON 结构，不涉及 schema 迁移。

前端消费的接口：GET `/feed`、`/topics`、`/topics/{slug}`、`/papers/{id}`、`/jobs/{id}`，POST `/papers/{id}/summary`，统一带 `/api/v1` 前缀。主题页复用 Feed 的 topic 参数。

## 行为约定

- 首次进入列表固定 since / until，切换榜单、主题及翻页继续使用同一窗口；点击最近 7/30 天重新以当前时间计算。
- 自定义日期按浏览器本地时区解释，结束日期包含当日，转换为次日零点的半开区间；最长 365 天。URL 使用带时区 ISO 8601。
- 指标 null / 缺失展示“暂无数据”，0 保持 0；前端不重新排序，不将引用数称为引用增速。
- Feed 只显示已收录且已分类的论文；总数属于当前筛选窗口，不表示数据源全部论文数。
- 引用按 paper_id + chunk_id 匹配，展示真实引文、章节、可用页码和上下文。证据来自摘要时不伪造页码。
- 论文及模型文本按纯文本渲染；外链仅允许 HTTP/HTTPS。没有内嵌 HTML、Markdown HTML 或 PDF 执行环境。
- 所有 HTTP 请求有 20 秒超时；页面切换取消过期查询，避免旧响应覆盖当前筛选结果。
- 活跃任务首次约 1 秒后查询，之后约每 2.5 秒轮询。完成、失败或跳过后停止轮询并刷新详情。
- 状态请求中断时暂停轮询，提供“恢复状态更新”，不自动再建任务；任务保存在后端，刷新页面可以恢复。
- 排队超过 60 秒仅提示尚未结束；没有 worker 心跳接口，不能据此判断 worker 离线。
- 再次分析由现有后端幂等接口及生成缓存处理；不提供强制绕过缓存功能。

## 检查与构建

```powershell
cd frontend
npm run typecheck
npm run lint
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

浏览器测试自动启动端口 4173 的构建预览（该端口需空闲），拦截 API 返回 fixture，不调用真实模型、不写数据库。浏览器测试前先 build。截图及失败 trace 位于被 Git 忽略的 `frontend/test-results/`。

后端检查在仓库根目录执行：

```powershell
uv run pytest
uv run ruff check .
uv run mypy app
```

集成测试仍只允许专用 Neon mvp-test 分支，配置与清理约定见 [NEON](NEON.md)。

构建产物位于 `frontend/dist/`。`npm run preview` 用于本地构建验收；公开部署需静态托管或反向代理提供 SPA 路由回退到 index.html，并将 `/api` 转发给 FastAPI（API 的 404 不得回退成 HTML）。本轮完成本地使用与构建验证，未部署公网服务。

## 验收结果

2026-09-11 验收通过：前端 11 项单元/组件测试、6 项 Chromium 浏览器测试；TypeScript、ESLint 和生产构建通过。后端 63 项单元测试及 5 项 Neon 集成测试分批验证通过，Ruff 和 mypy（39 个源文件）通过。

真实开发库联调显示 2 篇已分类论文；MindTopo 的已有摘要、比较、15 个证据区与 abstract-only 标记正常显示，浏览器无运行错误。其余已采集但未分类的论文不属于当前 Feed。真实联调未再次调用模型生成研究结论。

本机前端 `127.0.0.1:5173` 与 API `127.0.0.1:8000` 已启动，同时启动仅处理手动任务的 `worker --jobs-only`，不定时启动采集。进程记录及日志位于被忽略的 `.cache/`；这不是开机自启服务，重启后按本文命令恢复。

## Known limitations

- OpenReview 的真实采集 403 限制仍在；页面不假装所有数据源在线。
- worker 需单独运行，当前只有任务状态，没有 worker 在线检测。
- 前作比较仅覆盖已收录数据；部分分析为 abstract-only。
- 当前主题分类为两级导航；更深层级会继续展示，但不提供无限层级目录。
- 身份认证仍采用后端现有可选管理令牌，不是多用户权限系统。
- 榜单稳定性是固定时间基准，不是数据库快照；后台新增数据仍可能改变总数或排名。

## Next task

使用真实数据进行阅读体验反馈与研究结论抽样评估。后续功能和公开部署单独确定范围。
