export const PAGE_SIZE = 20

export function feedParams(input: URLSearchParams, now = new Date()): URLSearchParams {
  const params = new URLSearchParams(input)
  if (!params.has('until') && !params.has('since')) {
    params.set('until', now.toISOString())
    params.set('since', new Date(now.getTime() - 7 * 86_400_000).toISOString())
  }
  if (!params.has('type')) params.set('type', 'new')
  if (!params.has('offset')) params.set('offset', '0')
  params.set('limit', String(PAGE_SIZE))
  return params
}

export function filterError(params: URLSearchParams): string | undefined {
  const start = Date.parse(params.get('since') ?? '')
  const end = Date.parse(params.get('until') ?? '')
  if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end || end - start > 365 * 86_400_000)
    return '请选择有效日期，结束时间须晚于开始时间，范围不超过 365 天。'
  if (!['new', 'hot'].includes(params.get('type') ?? '')) return '榜单类型无效，请重置筛选。'
  if (!/^\d+$/.test(params.get('offset') ?? '') || !Number.isSafeInteger(Number(params.get('offset'))))
    return '页码无效，请重置筛选。'
}

export function localDate(value: string): string {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return ''
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

export function dateRange(start: string, inclusiveEnd: string): { since: string; until: string } | undefined {
  const since = new Date(`${start}T00:00:00`)
  const until = new Date(`${inclusiveEnd}T00:00:00`)
  until.setDate(until.getDate() + 1)
  if (!Number.isFinite(since.getTime()) || !Number.isFinite(until.getTime())) return undefined
  const range = { since: since.toISOString(), until: until.toISOString() }
  return filterError(new URLSearchParams({ ...range, type: 'new', offset: '0' })) ? undefined : range
}
