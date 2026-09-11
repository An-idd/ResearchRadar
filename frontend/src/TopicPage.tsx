import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { Topic } from './api'
import { FeedPage } from './FeedPage'
import { Loading, Notice } from './ui'
import { useResource } from './useResource'

export function TopicPage() {
  const { slug } = useParams()
  const [revision, setRevision] = useState(0)
  const result = useResource<Topic>(`/topics/${encodeURIComponent(slug ?? '')}`, revision)
  if (!result) return <Loading />
  if (result.error) return <Notice title={result.error} retry={() => setRevision(value => value + 1)} error><Link to="/">返回研究发现</Link></Notice>
  return <FeedPage topic={result.data!} />
}
