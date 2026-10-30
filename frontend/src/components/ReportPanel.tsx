// One-tap community reports (blueprint §10). No free text: reports describe the street, never people.
import { useState } from 'react'
import { api, type LatLon, type ReportKind, type ReportResult } from '../api'
import { deviceId } from '../lib/device'
import { getMyLocation } from '../lib/location'
import { ErrorState } from './States'

export const STREET_REPORTS: { kind: ReportKind; label: string; effect: string; fades: string }[] = [
  { kind: 'broken_light', label: 'Broken streetlight', effect: '−15', fades: 'until a photo shows it lit, or 7 days' },
  { kind: 'dark', label: 'Dark here', effect: '−15', fades: '3 hours' },
  { kind: 'deserted', label: 'Deserted / nobody around', effect: '−10', fades: '2 hours' },
  { kind: 'felt_unsafe', label: 'Felt unsafe here', effect: '−10', fades: '2 hours' },
  { kind: 'well_lit', label: 'Well lit and busy', effect: '+10', fades: '2 hours' },
]
export const REPORT_LABEL: Record<ReportKind, string> = {
  ...Object.fromEntries(STREET_REPORTS.map((r) => [r.kind, r.label])),
  place_closed: 'Place is closed',
  place_open: 'Place is open',
} as Record<ReportKind, string>

export function ReportPanel({
  point,
  picking,
  onPickOnMap,
  onSetPoint,
  onSent,
  at,
}: {
  at?: string
  point: LatLon | null
  picking: boolean
  onPickOnMap: () => void
  onSetPoint: (p: LatLon) => void
  onSent: () => void
}) {
  const [kind, setKind] = useState<ReportKind | null>(null)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [done, setDone] = useState<ReportResult | null>(null)
  const [locating, setLocating] = useState(false)

  const useMine = async () => {
    setLocating(true)
    setError(null)
    try {
      onSetPoint(await getMyLocation())
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLocating(false)
    }
  }

  const send = async () => {
    if (!kind || !point) return
    setSending(true)
    setError(null)
    try {
      setDone(await api.report({ kind, lat: point.lat, lon: point.lon, device_id: deviceId(), at }))
      onSent()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSending(false)
    }
  }

  if (done) {
    const info = STREET_REPORTS.find((r) => r.kind === done.kind)
    return (
      <div className="space-y-3" role="status">
        <p className="text-lg font-semibold">Thank you — you just helped the map.</p>
        <p className="text-sm text-ink-300">
          “{REPORT_LABEL[done.kind]}” on <strong className="text-ink-100">{done.street_name}</strong> ({info?.effect} points, fades after {info?.fades}).
          Its score for your walk time is now <strong className="text-ink-100">{Math.round(done.street_score_now ?? 0)}</strong>.
        </p>
        <button onClick={() => { setDone(null); setKind(null) }} className="min-h-11 w-full rounded-lg border border-ink-600 text-sm">Send another report</button>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-beacon-400">Report</p>
        <h2 className="mt-0.5 text-lg font-semibold">What is this street like right now?</h2>
        <p className="mt-1 text-xs text-ink-400">Describe the street, never people. Reports fade over time; a newer Sentinel photo outweighs them.</p>
      </div>
      <div className="grid grid-cols-1 gap-2">
        {STREET_REPORTS.map((r) => (
          <button key={r.kind} onClick={() => setKind(r.kind)} aria-pressed={kind === r.kind}
            className={`flex min-h-12 items-center justify-between rounded-xl border px-3 text-left text-sm ${kind === r.kind ? 'border-beacon-400 bg-beacon-400/10' : 'border-ink-700 bg-ink-900/60'}`}>
            <span className="text-ink-100">{r.label}</span>
            <span className="text-xs text-ink-400">{r.effect} · {r.fades}</span>
          </button>
        ))}
      </div>
      <div className="space-y-2">
        <p className="text-sm text-ink-300">{point ? `Location set: ${point.lat.toFixed(5)}, ${point.lon.toFixed(5)}` : 'Where is it?'}</p>
        <div className="grid grid-cols-2 gap-2">
          <button onClick={useMine} disabled={locating} className="min-h-11 rounded-lg border border-ink-600 text-sm disabled:opacity-50">
            {locating ? 'Finding you…' : 'Use my location'}
          </button>
          <button onClick={onPickOnMap} aria-pressed={picking}
            className={`min-h-11 rounded-lg border text-sm ${picking ? 'border-beacon-400 text-beacon-300' : 'border-ink-600'}`}>
            {picking ? 'Tap the map…' : 'Tap on the map'}
          </button>
        </div>
      </div>
      {error && <ErrorState title="Report not sent" message={error} />}
      <button onClick={send} disabled={!kind || !point || sending}
        className="min-h-12 w-full rounded-xl bg-beacon-400 font-semibold text-ink-950 disabled:opacity-40">
        {sending ? 'Sending…' : 'Send report'}
      </button>
    </div>
  )
}
