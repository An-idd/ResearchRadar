import { afterEach, describe, expect, it, vi } from 'vitest'
import { request, safeUrl } from '../src/api'
import { metricValue } from '../src/ui'

afterEach(() => vi.unstubAllGlobals())
describe('API boundary', () => {
  it('returns typed data and reports authentication failures without reflecting server secrets', async () => {
    const fetch = vi.fn().mockResolvedValueOnce(new Response('[{"slug":"agent"}]'))
      .mockResolvedValueOnce(new Response('private server error', { status: 401 }))
    vi.stubGlobal('fetch', fetch)
    expect(await request('/topics')).toEqual([{ slug: 'agent' }])
    await expect(request('/papers/id/summary', { method: 'POST' })).rejects.toThrow('访问令牌')
    expect(fetch.mock.calls[0][0]).toBe('/api/v1/topics')
  })
  it('rejects script URLs and distinguishes missing metrics from zero', () => {
    expect(safeUrl('javascript:alert(1)')).toBeUndefined()
    expect(safeUrl('https://arxiv.org/abs/123')).toBe('https://arxiv.org/abs/123')
    expect(metricValue(0)).toBe('0')
    expect(metricValue(null)).toBe('暂无数据')
  })
})
