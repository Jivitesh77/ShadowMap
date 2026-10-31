import { useCallback, useEffect, useRef, useState } from 'react'

export interface ApiState<T> {
  data: T | null
  error: string | null
  loading: boolean
  reload: () => void
}

/** Loads data from the backend and tracks loading / error state.
 *  Optionally refreshes every `pollMs`, and reloads whenever `key` changes (e.g. a chosen time). */
export function useApi<T>(load: () => Promise<T>, pollMs?: number, key?: string | number | null): ApiState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const loadRef = useRef(load)
  loadRef.current = load
  const latest = useRef(0) // only the newest request may update the state (an older, slower answer is dropped)

  const run = useCallback(async (showSpinner: boolean) => {
    const id = ++latest.current
    if (showSpinner) setLoading(true)
    try {
      const value = await loadRef.current()
      if (id !== latest.current) return
      setData(value)
      setError(null)
    } catch (err) {
      if (id !== latest.current) return
      setError((err as Error).message) // the last good data stays visible
    } finally {
      if (id === latest.current) setLoading(false)
    }
  }, [])

  useEffect(() => {
    run(true)
    if (!pollMs) return
    const id = setInterval(() => run(false), pollMs)
    return () => clearInterval(id)
  }, [run, pollMs, key])

  return { data, error, loading, reload: () => run(true) }
}
