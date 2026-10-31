import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import { ACCESS_CHANGED } from '../lib/accessCodes'
import { tabKeys } from '../lib/tabKeys'
import { getAccessCode, setAccessCode } from '../lib/sentinelAccess'
import { ErrorState } from '../components/States'
import { useApi } from '../hooks/useApi'
import { LiveSentinel } from '../components/LiveSentinel'
import { VideoSentinel } from '../components/VideoSentinel'
import { Badge, PageHeader } from '../components/Ui'

type Mode = 'video' | 'live'

// Sentinel data (photos, videos, rider routes) is only for the team: ask for the access code once.
function AccessGate({ onOk }: { onOk: () => void }) {
  const [code, setCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState(false)
  const check = async (e: React.FormEvent) => {
    e.preventDefault()
    setChecking(true)
    setError(null)
    setAccessCode(code.trim())
    try {
      await api.videoJobs()
      onOk()
    } catch (err) {
      setAccessCode(null)
      setError((err as ApiError).message)
    } finally {
      setChecking(false)
    }
  }
  return (
    <form onSubmit={check} className="mx-auto max-w-md space-y-3 rounded-2xl border border-ink-700 bg-ink-850 p-5">
      <h2 className="text-lg font-semibold">Sentinel access code</h2>
      <p className="text-sm text-ink-300">
        Sentinel photos, videos and rider routes are only for the ShadowMap team. The code is set in <code>backend/.env</code> (SENTINEL_TOKEN).
      </p>
      <input type="password" autoComplete="off" value={code} onChange={(e) => setCode(e.target.value)} aria-label="Sentinel access code"
        className="w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2" />
      {error && <ErrorState title="Not accepted" message={error} />}
      <button disabled={!code.trim() || checking} className="w-full rounded-xl bg-beacon-400 px-4 py-2.5 font-semibold text-ink-950 disabled:opacity-40">
        {checking ? 'Checking…' : 'Continue'}
      </button>
    </form>
  )
}

export default function SentinelPage() {
  const [mode, setMode] = useState<Mode>('video')
  const [unlocked, setUnlocked] = useState(() => !!getAccessCode())
  // Back to the code screen when the code is cleared: signing out, or the server no longer accepting it (api.ts).
  // Only ever locks: unlocking happens after the code screen has checked a code with the server.
  useEffect(() => {
    const sync = () => {
      if (!getAccessCode()) setUnlocked(false)
    }
    window.addEventListener(ACCESS_CHANGED, sync)
    return () => window.removeEventListener(ACCESS_CHANGED, sync)
  }, [])
  const status = useApi(api.sentinelStatus, 5000)
  const health = useApi(api.health)
  const open = health.data?.open_access === true // prototype: no access code on this server
  const pending = status.data?.observations_by_analysis.pending ?? 0

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader
        eyebrow="Sentinel"
        title="Be the eyes of the street"
        description="Riders share a street photo every few seconds, or a recorded night ride is turned into photos. An AI reads the lighting, activity and open places, and the map updates."
        aside={
          status.data && (
            <Badge tone={status.data.ai_configured ? 'ok' : 'warn'}>
              {pending} photo{pending === 1 ? '' : 's'} waiting for AI{status.data.ai_configured ? '' : ' · AI key not set'}
            </Badge>
          )
        }
      />
      <div className="rounded-xl border border-beacon-400/40 bg-ink-850 p-3 text-sm text-ink-300" role="note">
        <strong className="text-ink-100">Concept preview — not part of this prototype demo.</strong> Live rider photos and night-ride
        videos are our idea for keeping the map up to date. The screens are built and were checked only with test clips; no real
        footage has been used yet. Developing this needs support (riders, phones, testing and guidance).
      </div>

      {!unlocked && !open ? (
        health.loading ? null : <AccessGate onOk={() => setUnlocked(true)} />
      ) : (
      <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div role="tablist" aria-label="Sentinel mode" className="inline-flex rounded-xl border border-ink-700 bg-ink-900 p-1"
          onKeyDown={tabKeys(['video', 'live'] as const, mode, setMode)}>
          {(
            [
              ['video', 'Video mode'],
              ['live', 'Live mode'],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              role="tab"
              aria-selected={mode === m}
              tabIndex={mode === m ? 0 : -1}
              onClick={() => setMode(m)}
              className={`rounded-lg px-4 py-2 text-sm font-medium ${mode === m ? 'bg-beacon-400 text-ink-950' : 'text-ink-300 hover:text-ink-100'}`}
            >
              {label}
            </button>
          ))}
        </div>
        {!open && (
          <button onClick={() => setAccessCode(null)} className="rounded-lg border border-ink-600 px-3 py-2 text-sm font-medium text-ink-300 hover:bg-ink-800 hover:text-ink-100">
            Sign out of Sentinel
          </button>
        )}
      </div>

      {status.data && !status.data.ai_configured && (
        <div className="rounded-xl border border-ink-700 bg-ink-850 p-3 text-sm text-ink-300" role="note">
          <strong className="text-ink-100">AI analysis is not set up on this server (no Gemini key).</strong> Photos and video frames are
          still blurred and kept <strong>private</strong>; they are not analysed, so they do not change street colours yet. Maps, routes,
          reports and walks are not affected.
        </div>
      )}
      {mode === 'video' ? <VideoSentinel unavailable={status.data?.video_available === false ? status.data.video_note ?? 'Video mode is not available on this server.' : null} /> : <LiveSentinel />}
      </>
      )}
    </div>
  )
}
