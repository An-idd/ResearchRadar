import type { ReactNode } from 'react'
import { safeUrl } from './api'

export function ExternalLink({ href, children }: { href?: string | null; children: ReactNode }) {
  const url = safeUrl(href)
  return url ? <a href={url} target="_blank" rel="noopener noreferrer">{children} <span aria-hidden="true">↗</span></a> : null
}

export function Notice({ title, children, retry, error = false }: {
  title: string; children?: ReactNode; retry?: () => void; error?: boolean
}) {
  return <div className={`notice ${error ? 'notice-error' : ''}`} role={error ? 'alert' : 'status'}>
    <strong>{title}</strong>{children && <p>{children}</p>}
    {retry && <button className="button secondary" onClick={retry}>重试</button>}
  </div>
}

export function Loading() {
  return <div className="loading" role="status"><span className="spinner" />正在加载研究内容…</div>
}

export const metricLabels: Record<string, string> = {
  hf_upvotes: 'HF 赞同', citation_count: '引用数', openreview_rating: '评审评分',
  influential_citation_count: '高影响引用', relevance: '主题相关性', freshness: '新鲜度',
  novelty: '新颖性', source_quality: '来源质量',
}

export function metricValue(value: number | null | undefined): string {
  return value == null ? '暂无数据' : new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 2 }).format(value)
}

export function dateText(value: string): string {
  return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(value))
}
