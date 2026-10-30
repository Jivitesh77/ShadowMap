// Compare the shortest and the safest route (blueprint §8). Start and destination are chosen in PlanBar.
import type { LatLon, RouteResult, RouteSummary } from '../api'
import { SAFETY_COLOURS, STATUS_LABEL, categoryMeta, formatAge, formatDistance } from '../lib/mapMeta'
import { InfoIcon, RouteIcon } from './Icons'
import { BriefingPanel } from './BriefingPanel'
import { ErrorState, Skeleton } from './States'

export type PickTarget = 'start' | 'end' | 'report' | 'help' | null

export interface NamedPoint {
  label: string
  point: LatLon
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

function RouteCard({ kind, r, same }: { kind: 'safest' | 'shortest'; r: RouteSummary; same?: boolean }) {
  const safest = kind === 'safest'
  const title = same ? 'Suggested route (also the shortest)' : safest ? 'Suggested route' : 'Shortest route'
  const sub = safest ? 'Lowest cost by ShadowMap street scores, within 50% extra length' : 'Fewest metres, scores ignored'
  return (
    <div className={`rounded-2xl border p-4 ${safest ? 'border-beacon-400/50 bg-lavender-50' : 'border-ink-700 bg-ink-850'}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="flex items-center gap-2 font-semibold text-ink-100">
            <span className={safest ? 'h-1 w-5 rounded-full bg-beacon-400' : 'h-0 w-5 border-t-2 border-dotted border-ink-400'} aria-hidden="true" />
            {title}
          </p>
          <p className="mt-0.5 text-xs text-ink-400">{sub}</p>
        </div>
        <span className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${safest ? 'bg-beacon-400 text-white' : 'bg-ink-800 text-ink-300'}`}>
          {safest ? 'Safest by score' : 'Shortest'}
        </span>
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 text-sm">
        <div><dt className="text-[11px] text-ink-400">Walk</dt><dd className="font-semibold tabular-nums text-ink-100">{r.duration_min} min</dd></div>
        <div><dt className="text-[11px] text-ink-400">Distance</dt><dd className="font-semibold tabular-nums text-ink-100">{formatDistance(r.distance_m)}</dd></div>
        <div><dt className="text-[11px] text-ink-400">On red streets</dt><dd className={`font-semibold tabular-nums ${r.red_m > 0 ? 'text-danger' : 'text-ink-100'}`}>{r.red_m} m</dd></div>
      </dl>
      <div className="mt-3">
        <ColourBar r={r} />
        <p className="mt-1.5 flex flex-wrap justify-between gap-x-3 text-[11px] text-ink-400">
          <span>{r.places_passed_not_closed} places passed (not closed)</span>
          <span>{formatAge(r.freshest_photo_age_min)}</span>
        </p>
      </div>
    </div>
  )
}

function Comparison({ route }: { route: RouteResult }) {
  return (
    <div className="space-y-3">
      <RouteCard kind="safest" r={route.safest} same={route.same_route} />
      {!route.same_route && <RouteCard kind="shortest" r={route.shortest} />}
      <p className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-ink-400" aria-label="Street colour key">
        {(['green', 'yellow', 'red'] as const).map((c) => (
          <span key={c} className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-full" style={{ background: SAFETY_COLOURS[c] }} />
            {c === 'green' ? 'Green 70–100' : c === 'yellow' ? 'Yellow 40–69' : 'Red 0–39'}</span>
        ))}
        <span>· bar = share of the route's length</span>
      </p>
    </div>
  )
}

export function RoutePanel({
  start,
  end,
  route,
  loading,
  error,
  onRetry,
  at,
}: {
  start: LatLon | null
  end: LatLon | null
  route: RouteResult | null
  loading: boolean
  error: string | null
  onRetry: () => void
  at?: string
}) {
  const passed = route?.safest.places_passed ?? []
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-lg font-semibold text-ink-100">Route options</h2>
        <p className="text-xs text-ink-400">Suggested route first · scores from ShadowMap street data</p>
      </div>

      {!route && !loading && !error && (
        <p className="flex gap-2 rounded-xl bg-ink-900 p-3 text-sm text-ink-300">
          <RouteIcon size={18} className="mt-0.5 shrink-0 text-beacon-300" />
          {start || end
            ? 'Add the other point above to compare the shortest route with the safest one.'
            : 'Choose a starting point and a destination above — your location, a tap on the map or a named place. ShadowMap compares the shortest route with the safest one, on real streets.'}
        </p>
      )}

      {loading && (
        <div className="space-y-2" role="status">
          <span className="sr-only">Finding routes…</span>
          <Skeleton className="h-32 w-full" />
          <Skeleton className="h-32 w-full" />
        </div>
      )}
      {error && !loading && <ErrorState title="Can't plan this route" message={error} onRetry={onRetry} />}

      {route && !loading && !error && (
        <>
          <Comparison route={route} />
          {start && end && <BriefingPanel start={start} end={end} at={at} />}
          {route.notes.length > 0 && (
            <ul className="space-y-2">
              {route.notes.map((n) => (
                <li key={n} className="flex gap-2 rounded-lg bg-ink-900 p-2.5 text-sm text-ink-300">
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
            <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Places along the suggested route (within 50 m)</h3>
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
