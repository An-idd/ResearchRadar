import type { components } from './schema'

export type Topic = components['schemas']['TopicView']
export type Feed = components['schemas']['Feed']
export type FeedItem = components['schemas']['FeedItem']
export type PaperDetail = components['schemas']['PaperDetail']
export type Job = components['schemas']['JobView']
export type Evidence = components['schemas']['Evidence']
export type SourceText = components['schemas']['SourceText']

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const timeout = AbortSignal.timeout(20_000)
  const signal = init.signal ? AbortSignal.any([init.signal, timeout]) : timeout
  const response = await fetch(`/api/v1${path}`, { ...init, signal })
  if (!response.ok) {
    const messages: Record<number, string> = {
      401: '需要有效的访问令牌，请输入后重试。',
      404: '没有找到这项内容，它可能尚未收录。',
      422: '筛选参数无效，请检查日期范围。',
      429: '请求过于频繁，请稍后重试。',
    }
    throw new ApiError(response.status, messages[response.status] ?? '服务暂时不可用，请稍后重试。')
  }
  return response.json() as Promise<T>
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '连接中断或请求超时，请检查服务后重试。'
}

export function safeUrl(value: string | null | undefined): string | undefined {
  try {
    const url = new URL(value ?? '')
    return ['http:', 'https:'].includes(url.protocol) ? url.href : undefined
  } catch { return undefined }
}
