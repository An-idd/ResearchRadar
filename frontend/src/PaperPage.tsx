import { useCallback, useEffect, useState } from 'react'
import { Link, useLocation, useOutletContext, useParams } from 'react-router-dom'
import type { Evidence, PaperDetail, SourceText, Topic } from './api'
import { EvidenceList } from './EvidenceList'
import { dateText, ExternalLink, Loading, metricLabels, metricValue, Notice } from './ui'
import { useResource } from './useResource'
import { JobPanel } from './JobPanel'

function Claim({ field, title, value, evidence, sources }: {
  field: string; title: string; value: string | string[] | null | undefined; evidence: Evidence[]; sources: SourceText[]
}) {
  const empty = value == null || value.length === 0
  return <section className={`claim ${field === 'what_changed' ? 'claim-highlight' : ''}`}>
    <h3>{title}</h3>
    {empty ? <p className="muted">现有材料未提供足够信息。</p> : Array.isArray(value) ? <ul>{value.map((item, index) => <li key={index}>{item}</li>)}</ul> : <p>{value}</p>}
    {!empty && <EvidenceList evidence={evidence.filter(item => item.field === field)} sources={sources} />}
  </section>
}

const summaryFields = [
  ['what_changed', '这篇论文推进了什么'], ['problem', '研究问题'],
  ['why_problem_matters', '问题为何重要'], ['previous_approaches', '已有方法'],
  ['previous_limitations', '已有方法的局限'], ['method', '核心方法'],
  ['key_innovations', '关键创新'], ['experiment_setup', '实验设置'],
  ['key_results', '主要结果'], ['limitations', '局限与边界'],
  ['why_it_matters', '研究意义'], ['engineering_takeaways', '工程启示'],
] as const
const comparisonFields = [
  ['prior_state', '前作的方法'], ['current_change', '本篇的变化'],
  ['major_difference', '主要差异'], ['inherited_ideas', '沿用的想法'],
  ['new_ideas', '新增的想法'], ['tradeoffs', '代价与取舍'],
] as const

function Analysis({ detail }: { detail: PaperDetail }) {
  const { summary, comparison, generation } = detail
  if (!summary) return <Notice title="这篇论文还没有研究分析">生成后，可在这里阅读方法、创新、结果和原文证据。</Notice>
  return <>
    <section className="analysis-overview"><p className="eyebrow">THE CONTRIBUTION</p><h2>{summary.one_sentence}</h2>
      <div className="analysis-provenance"><span className="scope-badge">{generation?.scope === 'full-text' ? '基于全文片段' : generation?.scope === 'abstract-only' ? '仅基于摘要' : '分析范围未知'}</span>
        {generation && <span>分析于 {dateText(generation.created_at)}</span>}
      </div>
      <EvidenceList evidence={summary.evidence.filter(item => item.field === 'one_sentence')} sources={generation?.source_texts ?? []} />
    </section>
    <div className="section-title"><h2 id="analysis">研究分析</h2><span>理解贡献，也看清边界</span></div>
    <div className="analysis-sections">{summaryFields.map(([field, title]) => <Claim key={field} field={field} title={title} value={summary[field]} evidence={summary.evidence} sources={generation?.source_texts ?? []} />)}</div>
    <div className="section-title"><h2 id="comparison">与已有工作的比较</h2></div>
    {comparison ? <><p className="comparison-note">比较范围为库中已收录的相关前作。每条引用标注各自来源，前作可能仅提供摘要。</p><div className="analysis-sections">{comparisonFields.map(([field, title]) => <Claim key={field} field={field} title={title} value={comparison[field]} evidence={comparison.evidence} sources={generation?.comparison_sources ?? []} />)}</div></>
      : <Notice title={detail.comparison_status === 'insufficient-prior-papers' ? '暂时没有足够的相关前作' : '比较尚未生成'}>{detail.comparison_status === 'insufficient-prior-papers' ? '库中尚未收录可用于比较的同主题、更早论文。' : '已有摘要可以阅读，比较结果尚不可用。'}</Notice>}
    {generation && <details className="generation-details"><summary>分析信息</summary><dl><dt>模型</dt><dd>{generation.model}</dd><dt>生成方式</dt><dd>{generation.provider}</dd><dt>提示词版本</dt><dd>{generation.prompt_version}</dd></dl><p>模型自评置信度：{Math.round(summary.confidence * 100)}%。此数值不是经过校准的正确率；引用存在也不代表结论一定充分成立。</p></details>}
  </>
}

export function PaperPage() {
  const { id } = useParams()
  const location = useLocation()
  const topics = useOutletContext<Topic[]>()
  const [revision, setRevision] = useState(0)
  const refresh = useCallback(() => setRevision(value => value + 1), [])
  const result = useResource<PaperDetail>(`/papers/${encodeURIComponent(id ?? '')}`, revision)
  useEffect(() => { window.scrollTo(0, 0) }, [id])
  useEffect(() => { document.title = `${result?.data?.paper.title ?? '论文详情'} · ResearchRadar` }, [result?.data?.paper.title])
  const candidate: unknown = location.state?.backTo
  const backTo = typeof candidate === 'string' && (candidate.startsWith('/?') || candidate.startsWith('/topics/') || candidate === '/') ? candidate : '/'
  if (!result) return <Loading />
  if (result.error) return <Notice title={result.error} retry={refresh} error><Link to="/">返回研究发现</Link></Notice>
  const detail = result.data!
  const names = new Map(topics.map(topic => [topic.slug, topic.name]))
  return <div className="paper-detail"><Link className="back-link" to={backTo}>← 返回论文列表</Link>
    <div className="detail-heading"><p className="eyebrow">PAPER INTELLIGENCE</p><h1>{detail.paper.title}</h1><p className="authors">{detail.paper.authors.join(' · ') || '作者信息暂无'}</p>
      <div className="detail-meta"><time dateTime={detail.paper.published_at}>{dateText(detail.paper.published_at)}</time>{detail.paper.venue && <span>{detail.paper.venue}</span>}<ExternalLink href={detail.paper.paper_url}>论文原文</ExternalLink><ExternalLink href={detail.paper.pdf_url}>PDF</ExternalLink></div>
      <div className="tags">{detail.topics.map(slug => <Link className="tag" key={slug} to={`/topics/${slug}`}>{names.get(slug) ?? slug}</Link>)}</div>
    </div>
    <details className="abstract-block"><summary>阅读原始摘要</summary><p>{detail.paper.abstract ?? '暂无原始摘要。'}</p></details>
    <JobPanel key={detail.paper.id} paperId={detail.paper.id} initialJob={detail.job} hasSummary={!!detail.summary} onComplete={refresh} />
    <Analysis detail={detail} />
    <div className="section-title"><h2>来源与研究信号</h2></div>
    <section className="source-panel"><div className="source-links">{detail.sources.map(source => <span className="tag" key={`${source.source}/${source.source_id}`}>{source.source} · {source.source_id}</span>)}</div>
      {detail.metrics.length ? <div className="table-scroll"><table><thead><tr><th>指标</th><th>数值</th><th>来源</th><th>采样日期</th></tr></thead><tbody>{detail.metrics.map((metric, index) => <tr key={index}><td>{metricLabels[metric.name] ?? metric.name}</td><td>{metricValue(metric.value)}</td><td>{metric.source}</td><td>{dateText(metric.observed_at)}</td></tr>)}</tbody></table></div> : <p className="muted small">暂无可用指标；缺失不代表零。</p>}
    </section>
  </div>
}
