import { useEffect, useState } from 'react'
import { errorMessage, request } from './api'

export function useResource<T>(path: string, revision = 0) {
  const [result, setResult] = useState<{ path: string; revision: number; data?: T; error?: string }>()
  useEffect(() => {
    const controller = new AbortController()
    request<T>(path, { signal: controller.signal }).then(
      data => { if (!controller.signal.aborted) setResult({ path, revision, data }) },
      error => { if (!controller.signal.aborted) setResult({ path, revision, error: errorMessage(error) }) },
    )
    return () => controller.abort()
  }, [path, revision])
  return result?.path === path && result.revision === revision ? result : undefined
}
