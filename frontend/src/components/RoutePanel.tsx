// Choose start + destination, then compare the shortest and the safest route (blueprint §8).
import type { LatLon, RouteResult, RouteSummary } from '../api'
import { SAFETY_COLOURS, STATUS_LABEL, categoryMeta, formatAge, formatDistance } from '../lib/mapMeta'
import { InfoIcon, RouteIcon, XIcon } from './Icons'
import { ErrorState, Skeleton } from './States'

export type PickTarget = 'start' | 'end' | null

function PointButton({
  label,
  letter,
  value,
  active,
  onClick,
}: {
  label: string
  letter: 'A' | 'B'
  value: LatLon | null
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      aria-pressed={active}
      className={`flex w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors ${
        active ? 'border-beacon-400 bg-beacon-400/10' : 'border-ink-700 bg-ink-900/60 hover:border-ink-600'
      }`}
    >
      <span className="grid h-7 w-7 shrink-0 place-items-center rounded-full border-2 border-beacon-400 bg-white text-xs font-bold text-ink-950">
        {letter}
      </span>
      <span className="min-w-0">
        <span className="block text-xs text-ink-400">{label}</span>
        <span className="block truncate text-sm text-ink-100">
          {active ? 'Tap the map…' : value ? `${value.lat.toFixed(5)}, ${value.lon.toFixed(5)}` : 'Not set — tap to choose'}
        </span>
      </span>
    </button>
  )
}

function ColourBar({ r }: { r: RouteSummary }) {
  const total = r.metres_by_colour.green + r.metres_by_colour.yellow + r.metres_by_colour.red || 1
  return (
    <div className="flex h-1.5 w-full overflow-hidden rounded-full bg-ink-700" aria-hidden="true">
      {(['green', 'yellow', 'red'] as const).map((c) => (
        <span key={c} style={{ width: `${(r.metres_by_colour[c] / total) * 100}%`, background: SAFETY_COLOURS[c] }} />
      ))}
    </div>
  )
}

function Comparison({ route }: { route: RouteResult }) {
  const rows: [string, (r: RouteSummary) => string][] = [
    ['Distance', (r) => formatDistance(r.distance_m)],
    ['Walking time', (r) => `${r.duration_min} min`],
    ['On red streets', (r) => `${r.red_m} m`],
    ['Places passed (not closed)', (r) => String(r.places_passed_not_closed)],
    ['Freshest photo', (r) => formatAge(r.freshest_photo_age_min)],
  ]
  return (
    <div className="overflow-hidden rounded-xl border border-ink-700">
      <table className="w-full text-sm">
        <thead>
          <tr className="bg-ink-900/70 text-xs text-ink-400">
            <th className="px-3 py-2 text-left font-medium" />
            <th className="px-3 py-2 text-right font-medium">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-0 w-4 border-t-2 border-dotted border-ink-100" />
                Shortest
              </span>
            </th>
            <th className="px-3 py-2 text-right font-medium text-beacon-300">
              <span className="inline-flex items-center gap-1.5">
                <span className="h-1 w-4 rounded-full bg-beacon-400" />
                Safest
              </span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-700">
          {rows.map(([label, f]) => (
            <tr key={label}>
              <td className="px-3 py-2 text-ink-400">{label}</td>
              <td className="px-3 py-2 text-right tabular-nums text-ink-100">{f(route.shortest)}</td>
              <td className="px-3 py-2 text-right font-medium tabular-nums text-ink-100">{f(route.safest)}</td>
            </tr>
          ))}
          <tr>
            <td className="px-3 py-2 text-ink-400">Street colours</td>
            <td className="px-3 py-2">
              <ColourBar r={route.shortest} />
            </td>
            <td className="px-3 py-2">
              <ColourBar r={route.safest} />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

export function RoutePanel({
  start,
  end,
  picking,
  setPicking,
  onClear,
  route,
  loading,
  error,
  onRetry,
}: {
  start: LatLon | null
  end: LatLon | null
  picking: PickTarget
  setPicking: (p: PickTarget) => void
  onClear: () => void
  route: RouteResult | null
  loading: boolean
  error: string | null
  onRetry: () => void
}) {
  const passed = route?.safest.places_passed ?? []
  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wider text-beacon-400">Route</p>
          <h2 className="mt-0.5 text-lg font-semibold text-ink-100">Shortest vs safest</h2>
        </div>
        {(start || end) && (
          <button onClick={onClear} className="inline-flex items-center gap-1 rounded-lg px-2 py-1 text-sm text-ink-300 hover:bg-ink-700">
            <XIcon size={16} /> Clear
          </button>
        )}
      </div>

      <div className="space-y-2">
        <PointButton label="Start" letter="A" value={start} active={picking === 'start'} onClick={() => setPicking(picking === 'start' ? null : 'start')} />
        <PointButton label="Destination" letter="B" value={end} active={picking === 'end'} onClick={() => setPicking(picking === 'end' ? null : 'end')} />
      </div>

      {!start && !end && !picking && (
        <p className="flex gap-2 text-sm text-ink-400">
          <RouteIcon size={18} className="shrink-0" />
          Choose a start and a destination on the map. ShadowMap finds the shortest route and the safest one, on real streets.
        </p>
      )}

      {loading && (
        <div className="space-y-2" role="status">
          <span className="sr-only">Finding routes…</span>
          <Skeleton className="h-28 w-full" />
        </div>
      )}
      {error && !loading && <ErrorState title="Can't plan this route" message={error} onRetry={onRetry} />}

      {route && !loading && !error && (
        <>
          <Comparison route={route} />
          {route.notes.length > 0 && (
            <ul className="space-y-2">
              {route.notes.map((n) => (
                <li key={n} className="flex gap-2 rounded-lg bg-ink-900/60 p-2.5 text-sm text-ink-300">
                  <InfoIcon size={16} className="mt-0.5 shrink-0 text-beacon-300" />
                  {n}
                </li>
              ))}
            </ul>
          )}
          {(route.start.snap_distance_m > 30 || route.end.snap_distance_m > 30) && (
            <p className="text-xs text-ink-400">
              Points were moved to the nearest mapped street ({route.start.snap_distance_m} m and {route.end.snap_distance_m} m away).
            </p>
          )}
          <div>
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Places along the safest route (within 50 m)</h3>
            {passed.length === 0 ? (
              <p className="mt-1.5 text-sm text-ink-400">None recorded along this route.</p>
            ) : (
              <ul className="mt-1.5 space-y-1 text-sm">
                {passed.map((p) => (
                  <li key={p.id} className="flex justify-between gap-2">
                    <span className="truncate text-ink-100">{p.name || categoryMeta(p.category).label}</span>
                    <span className="shrink-0 text-xs text-ink-400">
                      {categoryMeta(p.category).label} · {STATUS_LABEL[p.status]}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <p className="text-xs text-ink-400">ShadowMap describes conditions; it never promises a route is safe.</p>
        </>
      )}
    </div>
  )
}
