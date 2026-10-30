// Side panel content for the map: area overview, street details, place details.
import type { ReactNode } from 'react'
import { api, type MapData, type Place } from '../api'
import { useApi } from '../hooks/useApi'
import {
  CATEGORY_ORDER,
  ROAD_CLASS,
  SAFETY_COLOURS,
  SAFETY_LABEL,
  STATUS_LABEL,
  categoryMeta,
  formatAge,
  formatDistance,
  osmUrl,
  placeName,
  roadTypeLabel,
  statusExplanation,
} from '../lib/mapMeta'
import { GooglePlacesPanel } from './GooglePlacesPanel'
import { InfoIcon, XIcon } from './Icons'
import type { Selection } from './MapView'
import { ErrorState, LoadingBlock } from './States'

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex justify-between gap-4 py-2 text-sm">
      <dt className="shrink-0 text-ink-400">{label}</dt>
      <dd className="text-right text-ink-100">{children}</dd>
    </div>
  )
}

function StatusPill({ status }: { status: Place['status'] }) {
  const cls = {
    open: 'bg-beacon-400 text-ink-950',
    closed: 'bg-ink-700 text-ink-300',
    unknown: 'border border-dashed border-beacon-400 text-beacon-300',
  }[status]
  return <span className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${cls}`}>{STATUS_LABEL[status]}</span>
}

const CONFIDENCE_STYLE = {
  high: 'bg-ink-100 text-ink-950',
  medium: 'bg-ink-700 text-ink-100',
  low: 'border border-ink-600 text-ink-300',
} as const

function formatDate(iso: string | null): string {
  if (!iso) return 'unknown'
  const d = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

function SourceTags({ p }: { p: Place }) {
  return (
    <>
      {p.sources.includes('shadowmap') && (
        <span className="rounded-md bg-ink-100 px-2 py-0.5 text-xs font-semibold text-ink-950">ShadowMap verified</span>
      )}
      {p.sources.includes('osm') && <span className="rounded-md bg-ink-700 px-2 py-0.5 text-xs font-medium text-ink-300">OpenStreetMap</span>}
    </>
  )
}

function PanelHeader({ kicker, title, onClose }: { kicker: string; title: string; onClose: () => void }) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-beacon-400">{kicker}</p>
        <h2 className="mt-0.5 text-lg font-semibold text-ink-100">{title}</h2>
      </div>
      <button onClick={onClose} aria-label="Close details" className="rounded-lg p-1.5 text-ink-400 hover:bg-ink-700 hover:text-ink-100">
        <XIcon size={18} />
      </button>
    </div>
  )
}

export function PlaceInfo({ p, onClose }: { p: Place; onClose: () => void }) {
  const link = osmUrl(p.osm_id)
  return (
    <div>
      <PanelHeader kicker={categoryMeta(p.category).label} title={placeName(p)} onClose={onClose} />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <StatusPill status={p.status} />
        <SourceTags p={p} />
        {!p.in_demo_area && <span className="rounded-md bg-ink-800 px-2 py-0.5 text-xs text-ink-300">Outside demo area</span>}
      </div>
      <p className="mt-3 text-sm text-ink-300">{statusExplanation(p)}</p>

      <div className="mt-3 rounded-xl border border-ink-700 bg-ink-900/60 p-3">
        <div className="flex items-center justify-between gap-2">
          <p className="text-xs text-ink-400">Confidence this listing is accurate</p>
          <span className={`rounded-full px-2 py-0.5 text-xs font-semibold capitalize ${CONFIDENCE_STYLE[p.confidence]}`}>{p.confidence}</span>
        </div>
        <p className="mt-1 text-xs text-ink-300">{p.confidence_reason}</p>
        <p className="mt-1 text-xs text-ink-400">This is about the listing, not a safety rating of the place.</p>
      </div>

      <dl className="mt-3 divide-y divide-ink-700 border-t border-ink-700">
        <Row label="Listed hours">
          {p.opening_hours ? (
            <>
              {p.opening_hours}
              <span className="block text-xs text-ink-400">from {p.hours_source === 'shadowmap' ? 'ShadowMap team check' : 'OpenStreetMap'}</span>
            </>
          ) : (
            <span className="text-ink-400">Not listed</span>
          )}
        </Row>
        <Row label="Phone">{p.phone ?? <span className="text-ink-400">Not listed</span>}</Row>
        {p.distance_from_center_m != null && <Row label="From IIIT Guwahati">{formatDistance(p.distance_from_center_m)}</Row>}
        <Row label="Last verified by team">
          {p.verified_on ? (
            <>
              {formatDate(p.verified_on)}
              <span className="block text-xs text-ink-400">by {p.verified_by}</span>
            </>
          ) : (
            <span className="text-ink-400">Never checked in person</span>
          )}
        </Row>
        {p.sources.includes('osm') && <Row label="Last edited on OpenStreetMap">{formatDate(p.osm_last_edited)}</Row>}
        {p.note && <Row label="How it was checked">{p.note}</Row>}
        {p.match_note && <Row label="Matched with OpenStreetMap">{p.match_note}</Row>}
        {p.duplicate_osm_ids.length > 0 && <Row label="Merged OSM duplicates">{p.duplicate_osm_ids.join(', ')}</Row>}
        <Row label="Last seen open">
          <span className="text-ink-400">No Sentinel photo yet</span>
        </Row>
      </dl>
      {link && (
        <a href={link} target="_blank" rel="noreferrer" className="mt-3 inline-block text-sm text-beacon-300 hover:underline">
          View on OpenStreetMap ↗
        </a>
      )}
    </div>
  )
}

export function StreetInfo({ id, at, onClose, onPick }: { id: number; at?: string; onClose: () => void; onPick: (s: Selection) => void }) {
  const { data: s, error, loading, reload } = useApi(() => api.street(id, at), undefined, `${id}|${at ?? ''}`)
  if (error) return <ErrorState message={error} onRetry={reload} />
  if (loading || !s) return <LoadingBlock label="Loading street…" rows={5} />
  return (
    <div>
      <PanelHeader kicker="Street" title={s.name || 'Unnamed road'} onClose={onClose} />
      <div className="mt-3 rounded-xl border border-ink-700 bg-ink-900/60 p-3">
        <div className="flex items-baseline justify-between">
          <p className="text-xs text-ink-400">Safety score</p>
          <p className="text-xs text-ink-400">{formatAge(s.freshest_photo_age_min)}</p>
        </div>
        {s.score == null || !s.colour ? (
          <p className="mt-0.5 text-sm text-ink-100">Not available</p>
        ) : (
          <>
            <p className="mt-0.5 flex items-center gap-2">
              <span className="h-3 w-3 rounded-full" style={{ background: SAFETY_COLOURS[s.colour] }} />
              <span className="text-2xl font-semibold tabular-nums text-ink-100">{Math.round(s.score)}</span>
              <span className="text-sm text-ink-400">/ 100</span>
            </p>
            <p className="mt-1 text-xs text-ink-400">{SAFETY_LABEL[s.colour]}</p>
            <dl className="mt-2 space-y-0.5 border-t border-ink-700 pt-2 text-xs">
              <div className="flex justify-between"><dt className="text-ink-400">Map score</dt><dd className="text-ink-100">{s.map_score}</dd></div>
              <div className="flex justify-between">
                <dt className="text-ink-400">Photo score</dt>
                <dd className="text-ink-100">{s.photo_score != null ? `${s.photo_score} (weight ${s.photo_weight})` : 'No photos yet'}</dd>
              </div>
              <div className="flex justify-between">
                <dt className="text-ink-400">Community reports</dt>
                <dd className="text-ink-100">{s.report_adjustment ? (s.report_adjustment > 0 ? `+${s.report_adjustment}` : s.report_adjustment) : 'None active'}</dd>
              </div>
            </dl>
          </>
        )}
      </div>
      <dl className="mt-3 divide-y divide-ink-700">
        <Row label="Road class">{ROAD_CLASS[s.road_class].label}</Row>
        <Row label="OpenStreetMap type">{roadTypeLabel(s.road_type)}</Row>
        <Row label="Length">{formatDistance(s.length_m)}</Row>
        <Row label="Street lighting">
          {s.lit === 'yes' ? 'Mapped as lit' : s.lit === 'no' ? 'Mapped as unlit' : <span className="text-ink-400">Not recorded</span>}
        </Row>
        <Row label="Sentinel photos">{s.observations}</Row>
        <Row label="Community reports">{s.reports}</Row>
      </dl>
      <h3 className="mt-4 text-xs font-semibold uppercase tracking-wider text-ink-400">Places within 200 m</h3>
      {s.nearby_places.length === 0 ? (
        <p className="mt-2 text-sm text-ink-400">None recorded.</p>
      ) : (
        <ul className="mt-2 space-y-1">
          {s.nearby_places.map((p) => (
            <li key={p.id}>
              <button
                onClick={() => onPick({ kind: 'place', id: p.id })}
                className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-ink-800"
              >
                <span className="truncate text-ink-100">{placeName(p)}</span>
                <span className="shrink-0 text-xs text-ink-400">
                  {STATUS_LABEL[p.status]} · {formatDistance(p.distance_m ?? 0)}
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
      <a
        href={`https://www.openstreetmap.org/way/${s.osm_way_id}`}
        target="_blank"
        rel="noreferrer"
        className="mt-3 inline-block text-sm text-beacon-300 hover:underline"
      >
        View on OpenStreetMap ↗
      </a>
    </div>
  )
}

const HELP_CATEGORIES = ['police', 'hospital', 'pharmacy', 'fuel']

export function AreaOverview({ data, onPick }: { data: MapData; onPick: (s: Selection) => void }) {
  const inside = data.places.filter((p) => p.in_demo_area)
  const km = data.streets.reduce((t, s) => t + s.length_m, 0) / 1000
  const missing = HELP_CATEGORIES.filter((c) => !inside.some((p) => p.category === c))
  const nearest = HELP_CATEGORIES.map((c) =>
    data.places
      .filter((p) => p.category === c)
      .sort((a, b) => (a.distance_from_center_m ?? 0) - (b.distance_from_center_m ?? 0))[0],
  ).filter(Boolean) as Place[]
  const withHours = data.places.filter((p) => p.opening_hours).length
  const downloaded = data.source.downloaded_at_utc ? new Date(data.source.downloaded_at_utc).toLocaleDateString('en-IN', { dateStyle: 'medium' }) : '—'

  return (
    <div className="space-y-5">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-beacon-400">Demo area</p>
        <h2 className="mt-0.5 text-lg font-semibold text-ink-100">{data.source.area?.name ?? 'Map'}</h2>
        <p className="mt-1 text-sm text-ink-300">
          {data.streets.length} street segments ({km.toFixed(1)} km) · {inside.length} places inside the dashed box
        </p>
      </div>

      {missing.length > 0 && (
        <div className="flex gap-2.5 rounded-xl border border-beacon-400/30 bg-beacon-400/10 p-3 text-sm">
          <InfoIcon size={18} className="mt-0.5 shrink-0 text-beacon-300" />
          <p className="text-ink-100">
            OpenStreetMap lists no {missing.map((c) => categoryMeta(c).label.toLowerCase()).join(', ')} inside this area. The
            nearest ones are shown below. Places the team checks in person can be added and are marked “ShadowMap verified”.
          </p>
        </div>
      )}

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Nearest help</h3>
        <ul className="mt-2 space-y-1">
          {nearest.map((p) => (
            <li key={p.id}>
              <button
                onClick={() => onPick({ kind: 'place', id: p.id })}
                className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left hover:bg-ink-800"
              >
                <span
                  className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-ink-800 text-beacon-300 [&>svg]:h-4 [&>svg]:w-4"
                  dangerouslySetInnerHTML={{
                    __html: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${categoryMeta(p.category).icon}</svg>`,
                  }}
                />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-sm text-ink-100">{placeName(p)}</span>
                  <span className="block text-xs text-ink-400">
                    {categoryMeta(p.category).label} · {STATUS_LABEL[p.status]}
                  </span>
                </span>
                <span className="shrink-0 text-sm tabular-nums text-ink-300">{formatDistance(p.distance_from_center_m ?? 0)}</span>
              </button>
            </li>
          ))}
        </ul>
      </div>

      {data.source.area?.center && <GooglePlacesPanel center={data.source.area.center} />}

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Legend</h3>
        <ul className="mt-2 grid grid-cols-1 gap-2 text-sm text-ink-300 sm:grid-cols-2 lg:grid-cols-1">
          <li className="flex items-center gap-2.5"><span className="sm-pin sm-open !h-5 !w-5" />Open at chosen time</li>
          <li className="flex items-center gap-2.5"><span className="sm-pin sm-closed !h-5 !w-5" />Closed</li>
          <li className="flex items-center gap-2.5"><span className="sm-pin sm-unknown !h-5 !w-5" />Hours unknown</li>
          <li className="flex items-center gap-2.5"><span className="sm-pin sm-unknown sm-manual !h-5 !w-5" />Checked in person by ShadowMap</li>
          {(['green', 'yellow', 'red'] as const).map((c) => (
            <li key={c} className="flex items-center gap-2.5">
              <span className="h-1 w-5 shrink-0 rounded-full" style={{ background: SAFETY_COLOURS[c] }} />
              {SAFETY_LABEL[c].split(':')[0]}
            </li>
          ))}
          <li className="flex items-center gap-2.5"><span className="h-0 w-5 border-t-2 border-dashed border-beacon-400" />Demo area (2 × 2 km)</li>
        </ul>
        <p className="mt-2 text-xs text-ink-400">
          Street colours are safety scores (0–100). Until Sentinel photos or reports arrive, scores come from map data only.
        </p>
      </div>

      <div className="border-t border-ink-700 pt-3 text-xs text-ink-400">
        <p>
          Sources: OpenStreetMap (downloaded {downloaded}) · ShadowMap verified: {data.places.filter((p) => p.sources.includes('shadowmap')).length}.{' '}
          {withHours} of {data.places.length} places list opening hours.
        </p>
        <p className="mt-1">Categories: {CATEGORY_ORDER.map((c) => `${categoryMeta(c).plural} ${data.places.filter((p) => p.category === c).length}`).join(' · ')}</p>
      </div>
    </div>
  )
}
