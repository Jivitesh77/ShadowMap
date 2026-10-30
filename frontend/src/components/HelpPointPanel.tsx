// Nearest help point (blueprint §10 "nearest safe spot"): the closest place open at the walk time, reached on mapped
// streets. Places with unknown hours are never shown as open. Nothing here is called "safe".
import type { HelpPointResult, LatLon } from '../api'
import { STATUS_LABEL, categoryMeta, formatDistance } from '../lib/mapMeta'
import { ErrorState, Skeleton } from './States'

export function HelpPointPanel({
  from,
  picking,
  onUseMine,
  onPickOnMap,
  result,
  loading,
  error,
  locating,
}: {
  from: LatLon | null
  picking: boolean
  onUseMine: () => void
  onPickOnMap: () => void
  result: HelpPointResult | null
  loading: boolean
  error: string | null
  locating: boolean
}) {
  return (
    <div className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-beacon-400">Help point</p>
        <h2 className="mt-0.5 text-lg font-semibold">Nearest place open now</h2>
        <p className="mt-1 text-xs text-ink-400">Only places whose hours (or a recent report) say they are open. Reached along mapped streets.</p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <button onClick={onUseMine} disabled={locating} className="min-h-11 rounded-lg bg-beacon-400 text-sm font-semibold text-ink-950 disabled:opacity-50">
          {locating ? 'Finding you…' : 'From my location'}
        </button>
        <button onClick={onPickOnMap} aria-pressed={picking}
          className={`min-h-11 rounded-lg border text-sm ${picking ? 'border-beacon-400 text-beacon-300' : 'border-ink-600'}`}>
          {picking ? 'Tap the map…' : 'From a point on the map'}
        </button>
      </div>
      {from && <p className="text-xs text-ink-400">From {from.lat.toFixed(5)}, {from.lon.toFixed(5)}</p>}
      {loading && <Skeleton className="h-24 w-full" />}
      {error && <ErrorState title="Could not search" message={error} />}
      {result && !loading && (
        <div className="space-y-3">
          {result.best_open ? (
            <div className="rounded-xl border border-beacon-400/50 bg-beacon-400/10 p-3">
              <p className="text-xs text-beacon-300">Nearest open · route drawn on the map</p>
              <p className="text-base font-semibold text-ink-100">{result.best_open.name ?? categoryMeta(result.best_open.category).label}</p>
              <p className="text-sm text-ink-300">
                {categoryMeta(result.best_open.category).label} · {formatDistance(result.best_open.walk_m ?? 0)} · about {result.best_open.walk_min} min walk
                {result.best_open.status_basis === 'community' ? ' · open per a recent community report' : ''}
              </p>
            </div>
          ) : (
            <p className="rounded-xl border border-caution/40 bg-caution/10 p-3 text-sm text-ink-100">{result.message}</p>
          )}
          {result.unknown_hours.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Nearby, hours unknown (may be closed)</h3>
              <ul className="mt-1 space-y-1 text-sm">
                {result.unknown_hours.map((p) => (
                  <li key={p.id} className="flex justify-between gap-2">
                    <span className="truncate">{p.name ?? categoryMeta(p.category).label}</span>
                    <span className="shrink-0 text-xs text-ink-400">{formatDistance(p.walk_m ?? 0)} walk</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          {result.outside_mapped_area.length > 0 && (
            <div>
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Beyond the mapped streets</h3>
              <ul className="mt-1 space-y-1 text-sm">
                {result.outside_mapped_area.map((p) => (
                  <li key={p.id} className="flex justify-between gap-2">
                    <span className="truncate">{p.name ?? categoryMeta(p.category).label} · {categoryMeta(p.category).label}</span>
                    <span className="shrink-0 text-xs text-ink-400">{formatDistance(p.straight_line_m ?? 0)} straight line · {STATUS_LABEL[p.status]}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-1 text-xs text-ink-400">No walking route: these are outside the streets ShadowMap has mapped.</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
