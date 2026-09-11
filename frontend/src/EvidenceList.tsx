import { Link } from 'react-router-dom'
import type { Evidence, SourceText } from './api'

export function EvidenceList({ evidence, sources }: { evidence: Evidence[]; sources: SourceText[] }) {
  if (!evidence.length) return null
  return <details className="evidence"><summary>查看原文证据 <span>{evidence.length}</span></summary>
    {evidence.map((item, index) => {
      const source = sources.find(value => value.paper_id === item.paper_id && value.chunks.some(chunk => chunk.id === item.chunk_id))
      const chunk = source?.chunks.find(value => value.id === item.chunk_id)
      return <figure key={`${item.paper_id}/${item.chunk_id}/${index}`}>
        <blockquote>{item.quote}</blockquote>
        <figcaption><Link to={`/papers/${item.paper_id}`}>{source?.title ?? '查看来源论文'}</Link>
          <span>{source?.scope === 'abstract-only' ? '摘要' : chunk?.section ?? '来源片段'}{chunk?.page != null ? ` · 第 ${chunk.page} 页` : ''}</span>
        </figcaption>
        {chunk && <details className="source-context"><summary>展开上下文</summary><p>{chunk.text}</p></details>}
      </figure>
    })}
  </details>
}
