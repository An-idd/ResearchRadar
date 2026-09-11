import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useOutletContext, useSearchParams } from 'react-router-dom'
import type { Feed, FeedItem, Topic } from './api'
import { dateRange, feedParams, filterError, localDate, PAGE_SIZE } from './feedState'
import { useResource } from './useResource'
import { dateText, ExternalLink, Loading, metricLabels, metricValue, Notice } from './ui'

function DateFilter({ since, until, apply }: { since: string; until: string; apply: (values: Record<string, string>) => void }) {
  const [start, setStart] = useState(localDate(since))
  const [end, setEnd] = useState(localDate(new Date(Date.parse(until) - 1).toISOString()))
  const [error, setError] = useState('')
  return <details className="date-filter"><summary>自定义日期 <span aria-hidden="true">⌄</span></summary>
    <form className="date-form" onSubmit={event => {
      event.preventDefault()
      const range = dateRange(start, end)
      if (!range) { setError('日期范围需有效，且不超过 365 天。'); return }
      setError(''); apply(range)
    }}>
      <label>开始日期<input type="date" required value={start} onChange={event => setStart(event.target.value)} /></label>
      <label>结束日期（含当日）<input type="date" required value={end} onChange={event => setEnd(event.target.value)} /></label>
      <button className="button" type="submit">应用日期</button>
      {error && <p role="alert">{error}</p>}
    </form>
  </details>
}

function PaperCard({ item, rank, topics }: { item: FeedItem; rank: number; topics: Topic[] }) {
  const location = useLocation()
  const names = new Map(topics.map(topic => [topic.slug, topic.name]))
  return <article className="paper-card">
    <div className="rank" aria-label={`第 ${rank} 项`}>{String(rank).padStart(2, '0')}</div>
    <div className="paper-body">
      <div className="paper-meta"><time dateTime={item.paper.published_at}>{dateText(item.paper.published_at)}</time><span>·</span><span>{item.paper.venue || (item.paper.arxiv_id ? 'arXiv' : '研究论文')}</span>
        <span className={`analysis-tag ${item.summary ? 'ready' : ''}`}>{item.summary ? (item.summary.scope === 'abstract-only' ? '摘要分析' : '全文片段分析') : '待分析'}</span>
      </div>
      <h2><Link to={`/papers/${item.paper.id}`} state={{ backTo: location.pathname + location.search }}>{item.paper.title}</Link></h2>
      <p className="paper-description">{item.summary?.one_sentence ?? item.paper.abstract ?? '暂无摘要，查看原文了解详情。'}</p>
      {item.summary?.what_changed && <p className="change-preview"><span>研究进展</span>{item.summary.what_changed}</p>}
      <div className="paper-bottom"><div className="tags">{item.topics.map(slug => <Link key={slug} className="tag" to={`/topics/${slug}`}>{names.get(slug) ?? slug}</Link>)}</div>
        <div className="card-metrics"><span>HF 赞同 <b>{metricValue(item.metrics.hf_upvotes)}</b></span><span>引用 <b>{metricValue(item.metrics.citation_count)}</b></span></div>
      </div>
      <details className="score-details"><summary>排序依据 <span aria-hidden="true">↗</span></summary>
        <p>综合得分 {metricValue(item.score)}。缺失信号不参与计分，按可用权重归一化。</p>
        <ul>{Object.entries(item.explanation.signals).map(([key, value]) => <li key={key}>{metricLabels[key] ?? key}：{metricValue(value)}{item.explanation.available_weights[key] != null && ` · 权重 ${Math.round(item.explanation.available_weights[key] * 100)}%`}</li>)}</ul>
        <ExternalLink href={item.paper.paper_url}>阅读原文</ExternalLink>
      </details>
    </div>
  </article>
}

function FeedResults({ query, topics }: { query: string; topics: Topic[] }) {
  const [revision, setRevision] = useState(0)
  const result = useResource<Feed>(`/feed?${query}`, revision)
  const [, setSearch] = useSearchParams()
  if (!result) return <Loading />
  if (result.error) return <Notice title={result.error} retry={() => setRevision(v => v + 1)} error />
  const feed = result.data!
  return <>
    <div className="results-heading"><p><strong>{feed.total}</strong> 篇相关论文 <span>已收录 · 已分类</span></p><span>每页 {feed.limit} 篇</span></div>
    {feed.items.length === 0 ? <Notice title="这个范围还没有论文">试试其他研究方向或扩大时间范围。榜单仅展示已收录且已分类的论文。</Notice>
      : <div className="paper-list">{feed.items.map((item, index) => <PaperCard key={item.paper.id} item={item} rank={feed.offset + index + 1} topics={topics} />)}</div>}
    <nav className="pagination" aria-label="论文分页"><span>第 {Math.floor(feed.offset / feed.limit) + 1} 页 / 共 {Math.max(1, Math.ceil(feed.total / feed.limit))} 页</span><div>
      <button className="button secondary" disabled={feed.offset === 0} onClick={() => setSearch(previous => { const next = new URLSearchParams(previous); next.set('offset', String(Math.max(0, feed.offset - PAGE_SIZE))); return next })}>← 上一页</button>
      <button className="button secondary" disabled={feed.offset + feed.limit >= feed.total} onClick={() => setSearch(previous => { const next = new URLSearchParams(previous); next.set('offset', String(feed.offset + PAGE_SIZE)); return next })}>下一页 →</button>
    </div></nav>
  </>
}

export function FeedPage({ topic }: { topic?: Topic }) {
  const topics = useOutletContext<Topic[]>()
  const [search, setSearch] = useSearchParams()
  const params = useMemo(() => {
    const value = feedParams(search)
    if (topic) value.set('topic', topic.slug)
    return value
  }, [search, topic])
  const query = params.toString()
  const error = filterError(params)
  useEffect(() => { document.title = `${topic?.name ?? '研究发现'} · ResearchRadar` }, [topic?.name])
  useEffect(() => { if (search.toString() !== query) setSearch(query, { replace: true }) }, [search, query, setSearch])
  const apply = (values: Record<string, string>) => {
    const next = new URLSearchParams(params)
    Object.entries(values).forEach(([key, value]) => { if (value) next.set(key, value); else next.delete(key) })
    next.set('offset', '0'); setSearch(next)
  }
  const days = (count: number) => {
    const until = new Date()
    apply({ since: new Date(until.getTime() - count * 86_400_000).toISOString(), until: until.toISOString() })
  }
  return <>
    <div className="page-intro"><div><p className="eyebrow">{topic ? 'EXPLORE A RESEARCH DIRECTION' : 'YOUR RESEARCH, IN FOCUS'}</p>
      {topic?.parent && <Link className="parent-link" to={`/topics/${topic.parent}`}>← {topics.find(value => value.slug === topic.parent)?.name ?? topic.parent}</Link>}
      <h1>{topic?.name ?? '发现值得读的研究。'}</h1><p className="lead">{topic?.description ?? '从最新论文到关键进展，让每一次阅读更有方向。'}</p></div>
      <div className="intro-mark" aria-hidden="true"><span /><i /></div>
    </div>
    {topic && <div className="child-topics">{topics.filter(value => value.parent === topic.slug).map(child => <Link className="tag" to={`/topics/${child.slug}`} key={child.slug}>{child.name} ↗</Link>)}</div>}
    <div className="feed-toolbar"><div className="feed-tabs" role="group" aria-label="榜单类型"><button aria-pressed={params.get('type') === 'new'} onClick={() => apply({ type: 'new' })}><span aria-hidden="true">✧</span> 最新研究 <small>NEW</small></button><button aria-pressed={params.get('type') === 'hot'} onClick={() => apply({ type: 'hot' })}><span aria-hidden="true">↗</span> 热门论文 <small>HOT</small></button></div></div>
    <div className="filter-row">
      {!topic && <label className="topic-select"><span>研究方向</span><select aria-label="研究方向筛选" value={params.get('topic') ?? ''} onChange={event => apply({ topic: event.target.value })}><option value="">全部方向</option>{topics.map(value => <option key={value.slug} value={value.slug}>{value.name}</option>)}</select></label>}
      <div className="range-buttons"><button onClick={() => days(7)}>最近 7 天</button><button onClick={() => days(30)}>最近 30 天</button></div>
      {!error && <DateFilter key={`${params.get('since')}/${params.get('until')}`} since={params.get('since')!} until={params.get('until')!} apply={apply} />}
    </div>
    {!error && <p className="window-caption">发表时间：{dateText(params.get('since')!)} — {dateText(new Date(Date.parse(params.get('until')!) - 1).toISOString())} <span>本地时区 · 排序随所选窗口计算</span></p>}
    {error ? <Notice title={error} retry={() => setSearch({})} error /> : <FeedResults query={query} topics={topics} />}
  </>
}
