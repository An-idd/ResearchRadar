import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import { detail, feedItem, job, paper, topics } from '../fixtures'

async function mockApi(page: Page, settings: { pending?: boolean; failFeed?: boolean } = {}) {
  let ready = !settings.pending
  let posted = false
  let polls = 0
  const requests: URL[] = []
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    requests.push(url)
    const path = url.pathname.replace('/api/v1', '')
    if (path === '/topics') return route.fulfill({ json: topics })
    if (path.startsWith('/topics/')) {
      const topic = topics.find(value => value.slug === path.split('/')[2])
      return route.fulfill({ status: topic ? 200 : 404, json: topic ?? {} })
    }
    if (path === '/feed') {
      if (settings.failFeed) return route.fulfill({ status: 503, json: {} })
      const offset = Number(url.searchParams.get('offset') ?? 0)
      const items = Array.from({ length: offset ? 1 : 20 }, (_, i) => ({ ...feedItem, paper: { ...paper, id: i === 0 ? paper.id : `paper-${i}`, title: i === 0 ? paper.title : `Language Agent Research ${offset + i + 1}` } }))
      return route.fulfill({ json: { items, total: 21, limit: 20, offset, since: url.searchParams.get('since'), until: url.searchParams.get('until') } })
    }
    if (path.endsWith('/summary')) { posted = true; return route.fulfill({ status: 202, json: job }) }
    if (path.startsWith('/jobs/')) {
      polls++
      if (polls > 1) ready = true
      return route.fulfill({ json: { ...job, status: ready ? 'succeeded' : 'running' } })
    }
    if (path === `/papers/${paper.id}`) return route.fulfill({ json: ready ? { ...detail, job: posted ? { ...job, status: 'succeeded' } : null } : { ...detail, summary: null, comparison: null, generation: null, comparison_status: 'not-generated', job: posted ? job : null } })
    return route.fulfill({ status: 404, json: {} })
  })
  return requests
}

test('feed filtering, stable pagination, detail evidence and return navigation', async ({ page }) => {
  const requests = await mockApi(page)
  await page.goto('/')
  await expect(page.getByRole('heading', { name: '发现值得读的研究。' })).toBeVisible()
  await expect(page.locator('.paper-card')).toHaveCount(20)
  await expect(page.locator('.card-metrics').first()).toContainText('HF 赞同 0')
  await expect(page.locator('.card-metrics').first()).toContainText('暂无数据')
  await page.getByLabel('研究方向筛选').selectOption('agent')
  await page.getByRole('button', { name: /热门论文/ }).click()
  await expect(page).toHaveURL(/type=hot/)
  const until = new URL(page.url()).searchParams.get('until')
  await page.getByRole('button', { name: '下一页 →' }).click()
  await expect(page.locator('.paper-card')).toHaveCount(1)
  expect(new URL(page.url()).searchParams.get('until')).toBe(until)
  await page.getByRole('link', { name: paper.title, exact: true }).click()
  await expect(page.getByText('仅基于摘要', { exact: true })).toBeVisible()
  await page.locator('.claim').filter({ has: page.getByRole('heading', { name: '前作的方法', exact: true }) }).getByText('查看原文证据').click()
  await expect(page.getByText('Method · 第 3 页')).toBeVisible()
  await page.getByRole('link', { name: '← 返回论文列表' }).click()
  expect(new URL(page.url()).searchParams.get('offset')).toBe('20')
  expect(new URL(page.url()).searchParams.get('topic')).toBe('agent')
  expect(requests.some(url => url.searchParams.get('offset') === '20' && url.searchParams.get('until') === until)).toBe(true)
})

test('manual analysis survives reload and refreshes the result when complete', async ({ page }) => {
  const requests = await mockApi(page, { pending: true })
  await page.goto(`/papers/${paper.id}`)
  await page.getByRole('button', { name: '生成分析' }).click()
  await expect(page.getByText('等待处理', { exact: true })).toBeVisible()
  await page.reload()
  await expect(page.getByText('正在生成分析', { exact: true })).toBeVisible()
  await expect(page.getByText(detail.summary!.one_sentence, { exact: true })).toBeVisible({ timeout: 10_000 })
  expect(requests.filter(url => url.pathname.endsWith('/summary'))).toHaveLength(1)
})

test('topic page and production deep links work after refresh', async ({ page }) => {
  await mockApi(page)
  await page.goto('/topics/agent-memory')
  await expect(page.getByRole('heading', { name: 'Agent Memory', exact: true })).toBeVisible()
  await page.reload()
  await expect(page.locator('.paper-card')).toHaveCount(20)
  expect(new URL(page.url()).searchParams.get('topic')).toBe('agent-memory')
  await page.getByRole('link', { name: '← LLM Agents' }).click()
  await expect(page.getByRole('heading', { name: 'LLM Agents', exact: true })).toBeVisible()
})

test('custom dates, invalid queries and empty results have usable states', async ({ page }) => {
  await mockApi(page)
  await page.goto('/')
  await page.getByText('自定义日期', { exact: false }).click()
  await page.getByLabel('开始日期').fill('2026-09-01')
  await page.getByLabel('结束日期（含当日）').fill('2026-09-03')
  await page.getByRole('button', { name: '应用日期' }).click()
  await expect(page.locator('.window-caption')).toContainText('2026年9月1日')
  await page.route('**/api/v1/feed?**', route => route.fulfill({ json: { items: [], total: 0, offset: 0, limit: 20, since: '2026-09-01T00:00:00Z', until: '2026-09-04T00:00:00Z' } }))
  await page.getByRole('button', { name: '最近 30 天' }).click()
  await expect(page.getByText('这个范围还没有论文')).toBeVisible()
  await page.goto('/?since=bad&until=bad')
  await expect(page.getByRole('alert')).toContainText('有效日期')
})

test('network failures and unknown resources are recoverable', async ({ page }) => {
  await mockApi(page, { failFeed: true })
  await page.goto('/')
  await expect(page.getByRole('alert')).toContainText('服务暂时不可用')
  await page.goto('/topics/missing')
  await expect(page.getByRole('alert')).toContainText('没有找到')
  await page.goto('/papers/invalid')
  await expect(page.getByRole('alert')).toContainText('没有找到')
})

test('mobile navigation, long content, focus and screenshots', async ({ page }) => {
  await mockApi(page)
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/')
  await expect(page.locator('.paper-card')).toHaveCount(20)
  await expect(page.locator('.topic-nav')).not.toHaveAttribute('open')
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: '跳转到主要内容' })).toBeFocused()
  await page.screenshot({ path: 'test-results/mobile-feed.png', fullPage: false })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.goto(`/papers/${paper.id}`)
  await expect(page.getByRole('heading', { name: paper.title })).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true)
  await page.screenshot({ path: 'test-results/mobile-detail.png', fullPage: false })
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.goto('/')
  await expect(page.locator('.paper-card')).toHaveCount(20)
  await page.screenshot({ path: 'test-results/desktop-feed.png', fullPage: false })
})
