import { useState } from 'react'
import { Link, NavLink, Outlet, Route, Routes } from 'react-router-dom'
import type { Topic } from './api'
import { useResource } from './useResource'
import { Notice } from './ui'
import { FeedPage } from './FeedPage'
import { PaperPage } from './PaperPage'
import { TopicPage } from './TopicPage'

function Layout() {
  const [navOpen, setNavOpen] = useState(() => window.matchMedia('(min-width: 721px)').matches)
  const [revision, setRevision] = useState(0)
  const topics = useResource<Topic[]>('/topics', revision)
  const values = topics?.data ?? []
  const roots = values.filter(topic => !topic.parent || !values.some(value => value.slug === topic.parent))
  const ordered = roots.flatMap(topic => [topic, ...values.filter(value => value.parent === topic.slug)])
  const visibleTopics = [...ordered, ...values.filter(topic => !ordered.includes(topic))]
  return <div className="app-shell">
    <a className="skip-link" href="#main">跳转到主要内容</a>
    <aside className="sidebar">
      <Link to="/" className="brand"><img src="/favicon.svg" alt="" width="36" height="36" /><span>ResearchRadar<small>保持研究的敏锐度</small></span></Link>
      <nav aria-label="主要导航"><NavLink to="/" end className="nav-item">◫ <span>研究发现</span></NavLink></nav>
      <details className="topic-nav" open={navOpen} onToggle={event => setNavOpen(event.currentTarget.open)}>
        <summary>研究方向 <span aria-hidden="true">⌄</span></summary>
        <nav aria-label="研究方向">
          {visibleTopics.map(topic => <NavLink className={`nav-item ${topic.parent ? 'nav-child' : ''}`} to={`/topics/${topic.slug}`} key={topic.slug}>
            <span className="topic-dot" />{topic.name}
          </NavLink>)}
          {!topics && <p className="muted small">正在加载主题…</p>}
          {topics?.error && <Notice title="主题暂时不可用" retry={() => setRevision(v => v + 1)} error />}
        </nav>
      </details>
      <div className="sidebar-footer"><span className="status-dot" />研究工作台<small>发现 · 理解 · 追踪</small></div>
    </aside>
    <div className="workspace">
      <header className="topbar"><span>LLM RESEARCH INTELLIGENCE</span><span className="edition">个人研究工作台</span></header>
      <main id="main" tabIndex={-1}><Outlet context={topics?.data ?? []} /></main>
      <footer className="page-footer">ResearchRadar <span>每个结论，都有迹可循。</span></footer>
    </div>
  </div>
}

export function App() {
  return <Routes><Route element={<Layout />}>
    <Route index element={<FeedPage />} />
    <Route path="papers/:id" element={<PaperPage />} />
    <Route path="topics/:slug" element={<TopicPage />} />
    <Route path="*" element={<Notice title="页面不存在"><Link to="/">返回研究发现</Link></Notice>} />
  </Route></Routes>
}
