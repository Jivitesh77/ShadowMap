// Optional supplementary search on Google Places. Results stay in this list: they are never drawn on the
// OpenStreetMap/Leaflet map, never mixed with ShadowMap or OpenStreetMap places, and never saved (Google terms).
import { useState } from 'react'
import { api, type GoogleNearby } from '../api'
import { useApi } from '../hooks/useApi'
import { categoryMeta, formatDistance } from '../lib/mapMeta'
import { ErrorState, Skeleton } from './States'

// Google's required attribution when Places data is shown without a Google map: the words "Google Maps",
// untranslated, on one line, Roboto (or sans-serif) 400, 12–16 px, white / #1F1F1F / #5E5E5E.
function GoogleMapsAttribution() {
  return (
    <span translate="no" className="whitespace-nowrap" style={{ fontFamily: 'Roboto, Arial, sans-serif', fontWeight: 400, fontSize: 12, color: '#FFFFFF' }}>
      Google Maps
    </span>
  )
}

const RADII = [2000, 8000]

export function GooglePlacesPanel({ center }: { center: [number, number] }) {
  const status = useApi(api.googleStatus)
  const [radius, setRadius] = useState(2000)
  const [result, setResult] = useState<GoogleNearby | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const search = async () => {
    setLoading(true)
    setError(null)
    try {
      setResult(await api.googleNearby(center[0], center[1], radius))
    } catch (err) {
      setResult(null)
      setError((err as Error).message)
    } finally {
      setLoading(false)
    }
  }

  if (status.loading) return null
  if (!status.data?.configured) {
    return (
      <p className="text-xs text-ink-400">
        Extra place search on Google is not set up. ShadowMap is using OpenStreetMap and team-verified places only.
      </p>
    )
  }

  return (
    <section aria-labelledby="google-places-heading" className="rounded-xl border border-ink-700 bg-ink-900/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <h3 id="google-places-heading" className="text-xs font-semibold uppercase tracking-wider text-ink-400">
          More places nearby
        </h3>
        <GoogleMapsAttribution />
      </div>
      <p className="mt-1 text-xs text-ink-400">
        Listed here only — not shown on the ShadowMap map, not checked by ShadowMap, not saved.
      </p>
      <div className="mt-2 flex items-center gap-2">
        {RADII.map((r) => (
          <button
            key={r}
            onClick={() => setRadius(r)}
            aria-pressed={radius === r}
            className={`rounded-lg px-2.5 py-1 text-xs ${radius === r ? 'bg-ink-100 text-ink-950' : 'bg-ink-800 text-ink-300 hover:bg-ink-700'}`}
          >
            {formatDistance(r)}
          </button>
        ))}
        <button
          onClick={search}
          disabled={loading}
          className="ml-auto rounded-lg border border-ink-600 px-3 py-1 text-xs font-medium text-ink-100 hover:bg-ink-700 disabled:opacity-50"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </div>

      {loading && <Skeleton className="mt-3 h-16 w-full" />}
      {error && !loading && (
        <div className="mt-3">
          <ErrorState title="Google search failed" message={error} />
        </div>
      )}
      {result && !loading && (
        <div className="mt-3">
          {result.results.length === 0 ? (
            <p className="text-sm text-ink-400">No results within {formatDistance(result.radius_m)}.</p>
          ) : (
            <ul className="divide-y divide-ink-700">
              {result.results.map((p) => (
                <li key={p.place_id} className="py-2">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-sm text-ink-100">{p.name ?? 'Unnamed'}</span>
                    {p.distance_m != null && <span className="shrink-0 text-xs tabular-nums text-ink-400">{formatDistance(p.distance_m)}</span>}
                  </div>
                  <p className="truncate text-xs text-ink-400">
                    {p.category ? categoryMeta(p.category).label : (p.google_type ?? 'Place')}
                    {p.business_status && p.business_status !== 'OPERATIONAL' ? ` · ${p.business_status.toLowerCase().replace(/_/g, ' ')}` : ''}
                    {p.address ? ` · ${p.address}` : ''}
                  </p>
                  {p.google_maps_uri && (
                    <a href={p.google_maps_uri} target="_blank" rel="noreferrer" className="text-xs text-beacon-300 hover:underline">
                      Open in Google Maps ↗
                    </a>
                  )}
                </li>
              ))}
            </ul>
          )}
          <p className="mt-2 text-xs text-ink-400">Hours are not shown here; check them in Google Maps.</p>
        </div>
      )}
    </section>
  )
}
