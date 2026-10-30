// City / municipality dashboard (blueprint §11): dark-street hotspots and a ranked streetlight repair list.
import { API_BASE, api } from '../api'
import { withCity } from '../lib/city'
import { useApi } from '../hooks/useApi'
import { LightbulbIcon } from '../components/Icons'
import { EmptyState, ErrorState, LoadingBlock } from '../components/States'
import { Badge, PageHeader, Panel, Stat } from '../components/Ui'

const date = (iso: string | null) => (iso ? new Date(iso).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' }) : '—')

export default function CityPage() {
  const r = useApi(api.cityRepairs, 30000)
  const d = r.data
  const items = d?.items ?? []

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader eyebrow="Operations" title="City dashboard"
        description="Dark streets and broken streetlights, with evidence, ranked by how many people walk or route through them — fixing those helps the most people first."
        aside={<a href={`${API_BASE}${withCity('/api/city/repairs.csv')}`} download className="rounded-lg bg-beacon-400 px-4 py-2 text-sm font-semibold text-ink-950">Download CSV</a>} />

      {r.error && !d ? <ErrorState message={r.error} onRetry={r.reload} /> : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Streets on the repair list" value={d ? items.length : null} loading={r.loading && !d} />
          <Stat label="Broken-light reports (7 days)" value={d ? items.reduce((t, i) => t + i.broken_light_reports, 0) : null} loading={r.loading && !d} />
          <Stat label="Dark-street hotspots" value={d ? d.hotspots.length : null} loading={r.loading && !d} hint="dark on at least one night this week" />
          <Stat label="Possibly fixed" value={d ? items.filter((i) => i.status.startsWith('possibly')).length : null} loading={r.loading && !d} hint="newer photo shows light" />
        </div>
      )}

      {d && d.hotspots.length > 0 && (
        <Panel title="Dark-street hotspots (last 7 nights)">
          <ul className="grid gap-2 sm:grid-cols-2">
            {d.hotspots.map((h) => (
              <li key={h.street_id} className="flex items-center justify-between rounded-lg bg-ink-900/60 p-2.5 text-sm">
                <span>{h.name}</span><span className="text-ink-400">{h.nights_dark_last_7} night{h.nights_dark_last_7 === 1 ? '' : 's'} dark</span>
              </li>
            ))}
          </ul>
        </Panel>
      )}

      <Panel title="Streetlight repair list (ranked)">
        {r.loading && !d ? <LoadingBlock /> : items.length === 0 ? (
          <EmptyState icon={<LightbulbIcon size={22} />} title="No repairs to rank yet">
            Streets appear here once people report a broken streetlight or “dark here”, or Sentinel photos show dark streets or lights not working.
          </EmptyState>
        ) : (
          <ol className="space-y-3">
            {items.map((i) => (
              <li key={i.street_id} className="rounded-xl border border-ink-700 bg-ink-900/60 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="font-semibold"><span className="mr-2 text-beacon-300">#{i.rank}</span>{i.name} <span className="text-xs font-normal text-ink-400">· {i.road_class} · {i.length_m} m</span></p>
                  <Badge tone={i.status.startsWith('possibly') ? 'ok' : 'warn'}>{i.status}</Badge>
                </div>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-xs sm:grid-cols-4">
                  <div><dt className="text-ink-400">Broken-light reports</dt><dd>{i.broken_light_reports} ({i.independent_reporters} people)</dd></div>
                  <div><dt className="text-ink-400">“Dark here” reports</dt><dd>{i.dark_reports}</dd></div>
                  <div><dt className="text-ink-400">Nights dark (7)</dt><dd>{i.nights_dark_last_7}</dd></div>
                  <div><dt className="text-ink-400">Walks / routes through</dt><dd>{i.walks_through} / {i.routes_planned_through}</dd></div>
                </dl>
                <div className="mt-2 text-xs text-ink-300">
                  <p className="text-ink-400">Evidence (latest {date(i.latest_dark_utc)}):</p>
                  {i.evidence.length ? i.evidence.map((e) => (
                    <div key={e.observation_id} className="mt-1">
                      {e.photo_available && e.photo_url && <img src={API_BASE + e.photo_url} alt="Street photo, faces and plates blurred" loading="lazy" className="mb-1 max-w-xs rounded-md" />}
                      <p>• {e.description ?? `${e.lighting} lighting`} — {e.sentinel}, {date(e.captured_utc)}{!e.photo_available && <span className="text-ink-400"> (no public photo)</span>}</p>
                    </div>
                  )) : <p>Community reports only; no Sentinel photo of this street yet.</p>}
                </div>
                <a href={`https://www.openstreetmap.org/way/${i.osm_way_id}`} target="_blank" rel="noreferrer" className="mt-1 inline-block text-xs text-beacon-300 hover:underline">Location on OpenStreetMap ↗</a>
              </li>
            ))}
          </ol>
        )}
        {d && <p className="mt-3 text-xs text-ink-400">{d.note}</p>}
      </Panel>
    </div>
  )
}
