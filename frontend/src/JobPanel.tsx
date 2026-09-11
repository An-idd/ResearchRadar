import { useEffect, useRef, useState } from 'react'
import { errorMessage, request } from './api'
import type { Job } from './api'

const labels: Record<Job['status'], string> = {
  queued: '等待处理', running: '正在生成分析', succeeded: '分析任务已完成',
  skipped: '本次分析已跳过', failed: '分析生成失败',
}

export function JobPanel({ paperId, initialJob, hasSummary, onComplete }: {
  paperId: string; initialJob: Job | null; hasSummary: boolean; onComplete: () => void
}) {
  const [job, setJob] = useState(initialJob)
  const [token, setToken] = useState('')
  const [showToken, setShowToken] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const [pollRevision, setPollRevision] = useState(0)
  const [waiting, setWaiting] = useState(false)
  const submission = useRef<AbortController | null>(null)
  const active = job?.status === 'queued' || job?.status === 'running'
  const jobId = job?.id

  useEffect(() => () => submission.current?.abort(), [])
  useEffect(() => {
    if (!active || !jobId) return
    const controller = new AbortController()
    const started = Date.now()
    let timer: ReturnType<typeof setTimeout>
    async function poll() {
      try {
        const next = await request<Job>(`/jobs/${jobId}`, { signal: controller.signal })
        if (controller.signal.aborted) return
        setJob(next)
        setWaiting(Date.now() - started >= 60_000)
        if (next.status === 'queued' || next.status === 'running') timer = setTimeout(poll, 2500)
        else onComplete()
      } catch (failure) {
        if (!controller.signal.aborted) setPollError(errorMessage(failure))
      }
    }
    timer = setTimeout(poll, 1000)
    return () => { controller.abort(); clearTimeout(timer) }
  }, [jobId, active, pollRevision, onComplete])

  async function submit() {
    if (submission.current || active) return
    const controller = new AbortController()
    submission.current = controller
    setSubmitting(true); setError(''); setPollError('')
    try {
      const next = await request<Job>(`/papers/${paperId}/summary`, {
        method: 'POST', signal: controller.signal,
        headers: token.trim() ? { Authorization: `Bearer ${token.trim()}` } : {},
      })
      if (!controller.signal.aborted) { setJob(next); setWaiting(false) }
    } catch (failure) {
      if (!controller.signal.aborted) { setError(errorMessage(failure)); setShowToken(true) }
    } finally {
      submission.current = null
      if (!controller.signal.aborted) setSubmitting(false)
    }
  }

  return <section className="job-panel" aria-label="分析任务">
    <div className="job-row"><div><p className="job-title" role="status">{active && <span className="spinner" />}{job ? labels[job.status] : '读懂这篇论文的贡献'}</p>
      <p className="job-description">{job?.status === 'queued' ? '任务已保存，开始处理后会自动更新。' : job?.status === 'running' ? '正在整理研究贡献与证据，请稍候。' : job?.status === 'skipped' ? '这篇论文未通过本次分析筛选，尚未生成新的分析。' : job?.status === 'failed' ? '已有分析仍可阅读，可手动重试本次任务。' : hasSummary ? '已有结果可直接阅读；再次分析会复用有效缓存。' : '生成结构化摘要、前作比较和原文证据。'}</p>
    </div><button className="button" disabled={active || submitting} onClick={submit}>{submitting ? '正在提交…' : active ? '处理中…' : job?.status === 'failed' ? '重试分析' : hasSummary ? '再次分析' : '生成分析'}</button></div>
    {waiting && active && <p className="job-wait">任务尚未结束。可以稍后返回本页查看，等待时间不表示任务失败。</p>}
    {error && <p className="job-error" role="alert">{error}</p>}
    {pollError && <div className="job-error" role="alert">状态更新暂停：{pollError} 任务可能仍在后台运行。<button className="text-button" onClick={() => { setPollError(''); setPollRevision(value => value + 1) }}>恢复状态更新</button></div>}
    {!active && <details className="token-settings" open={showToken} onToggle={event => setShowToken(event.currentTarget.open)}><summary>访问令牌（按需）</summary>
      <label>服务启用保护时输入<input type="password" autoComplete="off" aria-label="访问令牌" value={token} onChange={event => setToken(event.target.value)} /></label><p>仅在本页内存中使用，离开页面后清除。</p>
    </details>}
  </section>
}
