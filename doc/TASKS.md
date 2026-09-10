# ResearchRadar Implementation Tasks

本文件是 Codex 的开发任务清单。

原则：

> 一次只完成一个阶段。每阶段测试通过以后再进入下一阶段。

不要一次性生成整个项目。

---

# Phase 0 — Bootstrap

## Task 0.1

初始化 Python 项目。

要求：

- Python 3.12
- uv / pyproject.toml
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL
- Pydantic Settings
- pytest
- ruff
- mypy

目录按照 `DEVELOPMENT.md` 创建。

## Acceptance

```bash
pytest
ruff check .
mypy app
```

全部通过。

`GET /health`：

```json
{
  "status": "ok"
}
```

---

# Phase 1 — Domain Model

实现：

- Paper
- Topic
- PaperTopic
- PaperMetric
- PaperSummary
- IngestionRun

建立 Alembic migration。

## Acceptance

可以：

```python
create_paper()
get_paper()
update_paper()
list_papers()
```

测试数据库 round-trip。

---

# Phase 2 — Collector Framework

首先实现：

```python
PaperCollector
RawPaper
```

然后：

```text
ArxivCollector
```

不要同时实现所有数据源。

## Acceptance

给定 Fixture：

```text
arxiv_response.xml
```

可以正确生成：

```python
list[RawPaper]
```

网络层和 Parser 分开。

---

# Phase 3 — Normalize + Dedup

实现：

```text
normalize_title
canonical_id
deduplicate
merge_metadata
```

优先：

```text
DOI
arXiv ID
exact normalized title
embedding fallback
```

## Acceptance

同一论文来自两个 source：

```text
Paper A from arXiv
Paper A from OpenReview
```

最终 Database 中：

```text
1 Canonical Paper
2 Source Records
```

---

# Phase 4 — Topic Classification

首先使用固定 Taxonomy。

流程：

```text
title + abstract
      ↓
keyword / embedding shortlist
      ↓
LLM classifier
      ↓
Topic[]
```

Structured Output：

```json
{
  "topics": [
    {
      "slug": "agent-memory",
      "confidence": 0.92
    }
  ]
}
```

低于：

```text
0.60
```

不自动关联。

## Acceptance

准备至少 30 篇 fixture papers。

验证：

- Agent
- RAG
- Reasoning

基本分类正确。

---

# Phase 5 — Ranking

实现：

```text
RelevanceScore
FreshnessScore
NewScore
HotScore
```

MVP Hot 指标允许只有：

- HF popularity
- citations
- freshness
- relevance

必须实现 missing metric weight normalization。

## Acceptance

测试：

```text
刚发表 + 高相关论文
```

New 排名靠前。

```text
发布时间稍旧但高社区热度论文
```

Hot 排名靠前。

---

# Phase 6 — Hugging Face + OpenReview

增加：

```text
HuggingFaceCollector
OpenReviewCollector
```

Semantic Scholar：

```text
EnrichmentProvider
```

不要将 Semantic Scholar enrichment 写进 collector。

## Acceptance

同一论文多个数据源能够 merge。

PaperMetric 可保存：

```text
hf_upvotes
citation_count
openreview_rating
```

---

# Phase 7 — LLM Provider

定义：

```python
LLMProvider
```

实现至少一个真实 Provider：

```text
OpenAIProvider
```

同时实现：

```text
FakeLLMProvider
```

供测试使用。

要求：

- Structured Output
- retry
- timeout
- usage tracking
- model name
- prompt version

## Acceptance

业务代码中不允许直接依赖 OpenAI SDK。

---

# Phase 8 — Paper Summarizer

首先只处理：

```text
title
abstract
```

跑通 Structured Summary。

然后增加全文 Parser。

输出：

```text
one_sentence
problem
previous_limitations
method
key_innovations
key_results
limitations
why_it_matters
engineering_takeaways
what_changed
confidence
```

## Acceptance

任何缺失字段：

Pydantic validation fail。

不得存储不完整 Summary。

---

# Phase 9 — Full-text Analysis

实现：

```text
PDF fetch
PDF parse
section extraction
```

抽取：

```text
Abstract
Introduction
Method
Experiment
Limitations
Conclusion
```

不要把整个 PDF 一次性塞给模型。

使用 section-aware chunking。

## Acceptance

能够对测试论文产生：

```text
FullTextDocument
```

并保留 section 信息。

---

# Phase 10 — Comparator

对于目标论文：

```text
embedding search
       ↓
same topic prior papers
       ↓
top 5
       ↓
LLM comparison
```

输出：

```text
prior_state
current_change
major_difference
inherited_ideas
new_ideas
tradeoffs
importance
```

## Acceptance

API：

```http
GET /papers/{id}
```

能够返回：

```json
{
  "summary": {},
  "comparison": {}
}
```

---

# Phase 11 — Feed API

实现：

```http
GET /feed?type=new
GET /feed?type=hot
GET /feed?type=new&topic=agent
```

每项返回：

```json
{
  "paper": {},
  "score": 0.91,
  "summary": {
    "one_sentence": "...",
    "what_changed": "..."
  }
}
```

## Acceptance

能够完整跑：

```text
collect
↓
dedup
↓
classify
↓
rank
↓
summary
↓
feed
```

这是 MVP 的第一个 End-to-End milestone。

---

# Phase 12 — ResearchEvent

实现：

```text
Paper Summary
+
Comparison
+
Evidence
      ↓
ResearchEventExtractor
```

原则：

没有 evidence 不生成 Event。

## Acceptance

Event 必须包含：

```text
paper_id
topic_id
type
previous_state
new_state
significance
evidence
```

---

# Phase 13 — Topic Timeline

```text
ResearchEvents
      ↓
sort by date
      ↓
cluster similar events
      ↓
Timeline
```

API：

```http
GET /topics/{slug}/timeline
```

## Acceptance

可以回答：

> Agent Memory 最近发生了哪些关键变化？

而不是简单返回论文列表。

---

# Phase 14 — Research Memory

增加：

```text
UserInterest
UserFeedback
PaperReadHistory
RecommendationHistory
```

用户行为：

```text
VIEW
READ
SAVE
LIKE
DISLIKE
SKIP
```

## Acceptance

用户连续 LIKE：

```text
agent-memory
```

之后相关论文 personalized score 明显提高。

---

# Phase 15 — Personalized Feed

实现：

```http
GET /feed?type=personal
```

加入 exploration。

至少 5% 推荐来自相邻或未知 Topic。

---

# Phase 16 — Digest

Daily：

```text
Top New
Top Hot
Important Research Events
```

Weekly：

```text
What happened this week?
Important papers
Topic changes
Emerging directions
```

不能简单把每天 Summary 拼接起来。

必须做：

```text
weekly aggregation
+
deduplication
+
change synthesis
```

---

# Phase 17 — Trend Engine

增加：

```text
paper velocity
citation velocity
community velocity
research event density
```

输出：

```text
RISING
STABLE
COOLING
```

注意：

Trend Engine 在 Feed 和 Paper Intelligence 之后开发。

---

# Phase 18 — Idea Discovery

可选。

ResearchRadar 首先是：

```text
Discover
Track
Read
Understand
Compare
Follow Progress
```

以后再增加：

```text
Research Gap
Opportunity
Idea
```

不要在 MVP 阶段实现。

---

# Recommended Commit Boundaries

建议 Codex 按以下 Commit：

```text
feat: bootstrap research radar backend

feat: add paper and topic domain models

feat: add collector abstraction and arxiv collector

feat: add paper normalization and deduplication

feat: add topic classification pipeline

feat: add new and hot ranking

feat: add huggingface and openreview collectors

feat: add semantic scholar enrichment

feat: add llm provider abstraction

feat: add structured paper summarization

feat: add full text paper parsing

feat: add prior work comparison

feat: expose research feed api

feat: extract research events

feat: add topic timeline

feat: add research memory

feat: add personalized ranking

feat: generate daily and weekly research digest
```

---

# Codex 工作方式

每个 Task：

1. 阅读 `DEVELOPMENT.md`
2. 阅读 `AGENTS.md`
3. 只实现当前 Task
4. 先检查已有实现
5. 不重构无关模块
6. 写测试
7. 运行测试
8. 运行 lint
9. 输出修改摘要

禁止：

```text
顺手实现下一阶段
```

禁止：

```text
为了未来扩展提前引入复杂框架
```

原则：

> Make the current architecture extensible, but only implement current requirements.