# Neon PostgreSQL 开发约定

项目：`square-fog-91407295`。

| 分支 | 用途 | 本地文件 |
| --- | --- | --- |
| production | 已关联的原始生产分支，本轮不迁移、不写测试数据 | `.env.local` |
| development | MVP 开发与真实数据验收 | `.env.development` |
| mvp-test | 可清空的专用自动化测试分支，2026-09-18 到期 | `.env.test` |

默认加载 `.env.development`。通过 `RADAR_ENV_FILE` 显式选择环境；不要把生产连接复制到测试配置。`.env.*`、`.neon` 都已加入 Git 忽略。

```powershell
neon env pull --project-id square-fog-91407295 --branch development --file .env.development
neon env pull --project-id square-fog-91407295 --branch mvp-test --file .env.test
uv sync
uv run alembic upgrade head
```

`DATABASE_URL` 是 SQLAlchemy 运行时连接；`DATABASE_URL_UNPOOLED` 是 Alembic 直连。保留 URL 中的 TLS 参数。连接使用 psycopg 3，禁用驱动自动 prepared statements，启用连接存活检查。迁移显式创建 pgvector 扩展，应用启动不执行 DDL。

测试分支到期后显式新建同名分支并重新拉取 URL。测试工具必须验证 `NEON_BRANCH=mvp-test`，并确认 endpoint 与开发及生产不同；只有此分支允许清空业务表。生产发布前先在新测试分支验证 Alembic 迁移，再显式选择生产环境执行迁移。

采集时间窗口筛选论文发布日期；指标的 `observed_at` 记录实际访问来源的时间。重跑不会新增重复论文或相同版本的分析；重新访问来源可能产生新的指标采样，这些是新的观察记录。

`neon.ts` 管理 Neon 服务配置；`neon deploy` 不部署 Python API，也不替代 Alembic。Python API 与 worker 在本机或常规 Python 主机运行。

Windows 若终端找不到 node/npm，可在当前 PowerShell 设置 `$env:Path = 'D:\node;' + $env:Path`。

参考：[Neon 连接池](https://neon.com/docs/connect/connection-pooling)、[SQLAlchemy psycopg](https://docs.sqlalchemy.org/en/20/dialects/postgresql.html#module-sqlalchemy.dialects.postgresql.psycopg)、[Codex 非交互模式](https://developers.openai.com/codex/noninteractive)。
