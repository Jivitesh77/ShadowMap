import { useState } from 'react'
import { api } from '../api'
import { useApi } from '../hooks/useApi'
import { LiveSentinel } from '../components/LiveSentinel'
import { VideoSentinel } from '../components/VideoSentinel'
import { Badge, PageHeader } from '../components/Ui'

type Mode = 'video' | 'live'

export default function SentinelPage() {
  const [mode, setMode] = useState<Mode>('video')
  const status = useApi(api.sentinelStatus, 5000)
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

      <div role="tablist" aria-label="Sentinel mode" className="inline-flex rounded-xl border border-ink-700 bg-ink-900 p-1">
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
            onClick={() => setMode(m)}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${mode === m ? 'bg-beacon-400 text-ink-950' : 'text-ink-300 hover:text-ink-100'}`}
          >
            {label}
          </button>
        ))}
      </div>

      {mode === 'video' ? <VideoSentinel /> : <LiveSentinel />}
    </div>
  )
}
