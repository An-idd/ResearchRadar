import { describe, expect, it } from 'vitest'
import { dateRange, feedParams, filterError } from '../src/feedState'

describe('shareable feed filters', () => {
  it('fixes the default window and retains it when paginating or switching ranking', () => {
    const first = feedParams(new URLSearchParams(), new Date('2026-09-11T12:00:00Z'))
    first.set('offset', '20'); first.set('type', 'hot')
    const second = feedParams(first, new Date('2026-09-12T12:00:00Z'))
    expect(second.get('until')).toBe('2026-09-11T12:00:00.000Z')
    expect(second.get('since')).toBe('2026-09-04T12:00:00.000Z')
    expect(second.get('offset')).toBe('20')
  })
  it('uses an exclusive next-day boundary for inclusive date inputs', () => {
    const range = dateRange('2026-09-10', '2026-09-10')!
    expect(new Date(range.since).getDate()).toBe(10)
    expect(new Date(range.until).getDate()).toBe(11)
    expect(dateRange('2026-09-11', '2026-09-10')).toBeUndefined()
    expect(dateRange('2020-01-01', '2026-01-01')).toBeUndefined()
  })
  it('rejects malformed URL filters without sending a request', () => {
    const params = feedParams(new URLSearchParams('since=garbage&until=no'))
    expect(filterError(params)).toContain('有效日期')
    const valid = feedParams(new URLSearchParams('offset=-1'))
    expect(filterError(valid)).toContain('页码')
  })
})
