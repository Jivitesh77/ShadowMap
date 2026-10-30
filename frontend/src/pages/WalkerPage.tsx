import { useMemo, useState } from 'react'
import { api } from '../api'
import { useApi } from '../hooks/useApi'
import { MapPinIcon } from '../components/Icons'
import { AreaOverview, PlaceInfo, StreetInfo } from '../components/MapPanels'
import { MapView, type Selection } from '../components/MapView'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { CATEGORY_ORDER, categoryMeta } from '../lib/mapMeta'

/** Today's date in India time, as YYYY-MM-DD. */
function todayIST(): string {
  return new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10)
}

function formatAt(at: string): string {
  const d = new Date(`${at}:00`)
  return d.toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

export default function WalkerPage() {
  const [at, setAt] = useState<string | undefined>(undefined) // undefined = now
  const map = useApi(() => api.map(at), at ? undefined : 60000, at ?? 'now')
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [openOnly, setOpenOnly] = useState(false)
  const [selection, setSelection] = useState<Selection>(null)

  const data = map.data
  const counts = useMemo(() => {
    const c: Record<string, number> = {}
    data?.places.forEach((p) => (c[p.category] = (c[p.category] ?? 0) + 1))
    return c
  }, [data])
  const visiblePlaces = useMemo(
    () => (data?.places ?? []).filter((p) => !hidden.has(p.category) && (!openOnly || p.status === 'open')),
    [data, hidden, openOnly],
  )
  const selectedPlace = selection?.kind === 'place' ? data?.places.find((p) => p.id === selection.id) : undefined
  const tonight = `${todayIST()}T23:30`

  const toggle = (cat: string) =>
    setHidden((h) => {
      const n = new Set(h)
      if (n.has(cat)) n.delete(cat)
      else n.add(cat)
      return n
    })

  return (
    <div className="mx-auto max-w-[1600px] space-y-4">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-beacon-400">Walker</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Plan a safer walk</h1>
        </div>

        {/* Time of the walk: open/closed is judged for this time, not for now */}
        <div className="flex flex-wrap items-center gap-2" role="group" aria-label="Time of walk">
          <span className="text-xs text-ink-400">Walk time (IST)</span>
          <button
            onClick={() => setAt(undefined)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${!at ? 'bg-beacon-400 text-ink-950' : 'bg-ink-800 text-ink-300 hover:bg-ink-700'}`}
          >
            Now
          </button>
          <button
            onClick={() => setAt(tonight)}
            className={`rounded-lg px-3 py-1.5 text-sm font-medium ${at === tonight ? 'bg-beacon-400 text-ink-950' : 'bg-ink-800 text-ink-300 hover:bg-ink-700'}`}
          >
            Tonight 11:30 pm
          </button>
          <input
            type="datetime-local"
            aria-label="Choose walk time"
            value={at ?? ''}
            onChange={(e) => setAt(e.target.value || undefined)}
            className="rounded-lg border border-ink-600 bg-ink-850 px-2 py-1.5 text-sm text-ink-100 [color-scheme:dark]"
          />
        </div>
      </header>

      {/* Category filters */}
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0" aria-label="Filter places">
        <button
          onClick={() => setOpenOnly((v) => !v)}
          aria-pressed={openOnly}
          className={`shrink-0 rounded-full px-3 py-1.5 text-sm font-medium ring-1 ring-inset ${
            openOnly ? 'bg-beacon-400 text-ink-950 ring-beacon-400' : 'text-ink-300 ring-ink-600 hover:bg-ink-800'
          }`}
        >
          Open at walk time only
        </button>
        <span className="mx-1 hidden w-px shrink-0 bg-ink-700 sm:block" />
        {CATEGORY_ORDER.map((cat) => {
          const n = counts[cat] ?? 0
          const on = !hidden.has(cat)
          return (
            <button
              key={cat}
              onClick={() => toggle(cat)}
              disabled={n === 0}
              aria-pressed={on && n > 0}
              className={`shrink-0 rounded-full px-3 py-1.5 text-sm ring-1 ring-inset disabled:cursor-not-allowed disabled:opacity-40 ${
                on ? 'bg-ink-700 text-ink-100 ring-ink-600' : 'text-ink-400 ring-ink-700 line-through'
              }`}
            >
              {categoryMeta(cat).plural} <span className="tabular-nums text-ink-400">{n}</span>
            </button>
          )
        })}
      </div>

      {map.error && !data ? (
        <ErrorState message={map.error} onRetry={map.reload} />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
          <div className="relative h-[62vh] min-h-[380px] min-w-0 overflow-hidden rounded-2xl border border-ink-700 lg:h-[calc(100vh-220px)]">
            {!data ? (
              <Skeleton className="h-full w-full rounded-none" />
            ) : data.streets.length === 0 ? (
              <div className="grid h-full place-items-center bg-ink-850 p-6">
                <EmptyState icon={<MapPinIcon size={22} />} title="No map data in the database">
                  Run the map build step (see README) to load the saved OpenStreetMap data.
                </EmptyState>
              </div>
            ) : (
              <>
                <MapView source={data.source} streets={data.streets} places={visiblePlaces} selection={selection} onSelect={setSelection} />
                <div className="pointer-events-none absolute top-3 left-14 z-[500] rounded-lg bg-ink-950/90 px-3 py-1.5 text-xs text-ink-300 ring-1 ring-ink-700">
                  Open/closed for <span className="font-semibold text-ink-100">{formatAt(data.at)}</span>
                  {map.loading && <span className="ml-2 text-beacon-300">updating…</span>}
                </div>
              </>
            )}
          </div>

          <aside className="min-w-0 rounded-2xl border border-ink-700 bg-ink-850 p-5 lg:h-[calc(100vh-220px)] lg:overflow-y-auto">
            {!data ? (
              <div className="space-y-3">
                <Skeleton className="h-5 w-2/5" />
                <Skeleton className="h-4 w-full" />
                <Skeleton className="h-4 w-4/5" />
              </div>
            ) : selection?.kind === 'street' ? (
              <StreetInfo id={selection.id} at={at} onClose={() => setSelection(null)} onPick={setSelection} />
            ) : selectedPlace ? (
              <PlaceInfo p={selectedPlace} onClose={() => setSelection(null)} />
            ) : (
              <AreaOverview data={data} onPick={setSelection} />
            )}
          </aside>
        </div>
      )}
    </div>
  )
}
