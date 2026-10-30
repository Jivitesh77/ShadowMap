import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, type HelpPointResult, type LatLon, type RouteResult } from '../api'
import { useApi } from '../hooks/useApi'
import { getMyLocation } from '../lib/location'
import { MapPinIcon } from '../components/Icons'
import { HelpPointPanel } from '../components/HelpPointPanel'
import { AreaOverview, PlaceInfo, StreetInfo } from '../components/MapPanels'
import { MapView, type Selection } from '../components/MapView'
import { ReportPanel } from '../components/ReportPanel'
import { RoutePanel, type NamedPoint, type PickTarget } from '../components/RoutePanel'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { CATEGORY_ORDER, categoryMeta, placeName } from '../lib/mapMeta'

type Tab = 'route' | 'report' | 'help'

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
  const [refresh, setRefresh] = useState(0) // bumped after a report so scores, routes and panels reload
  const map = useApi(() => api.map(at), at ? undefined : 60000, `${at ?? 'now'}|${refresh}`)
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const [openOnly, setOpenOnly] = useState(false)
  const [selection, setSelection] = useState<Selection>(null)
  const [tab, setTab] = useState<Tab>('route')
  const [picking, setPicking] = useState<PickTarget>(null)
  const panelRef = useRef<HTMLElement>(null)

  // Route planning
  const [start, setStart] = useState<LatLon | null>(null)
  const [end, setEnd] = useState<LatLon | null>(null)
  const [route, setRoute] = useState<RouteResult | null>(null)
  const [routeLoading, setRouteLoading] = useState(false)
  const [routeError, setRouteError] = useState<string | null>(null)
  const [locating, setLocating] = useState<'start' | 'end' | 'help' | null>(null)
  const [locError, setLocError] = useState<string | null>(null)

  // Report and help point
  const [reportPoint, setReportPoint] = useState<LatLon | null>(null)
  const [helpFrom, setHelpFrom] = useState<LatLon | null>(null)
  const [help, setHelp] = useState<HelpPointResult | null>(null)
  const [helpLoading, setHelpLoading] = useState(false)
  const [helpError, setHelpError] = useState<string | null>(null)

  const findRoute = useCallback(async () => {
    if (!start || !end) return
    setRouteLoading(true)
    setRouteError(null)
    try {
      setRoute(await api.route(start, end, at))
    } catch (err) {
      setRoute(null)
      setRouteError((err as Error).message)
    } finally {
      setRouteLoading(false)
    }
  }, [start, end, at])

  useEffect(() => {
    if (start && end) findRoute()
    else setRoute(null)
  }, [findRoute, start, end, refresh])

  const findHelp = useCallback(async () => {
    if (!helpFrom) return
    setHelpLoading(true)
    setHelpError(null)
    try {
      setHelp(await api.helpPoint(helpFrom, at))
    } catch (err) {
      setHelp(null)
      setHelpError((err as Error).message)
    } finally {
      setHelpLoading(false)
    }
  }, [helpFrom, at])

  useEffect(() => {
    findHelp()
  }, [findHelp, refresh])

  const showPanel = (t: Tab) => {
    setTab(t)
    setSelection(null)
    if (window.innerWidth < 1024) setTimeout(() => panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }

  const onPick = (p: LatLon) => {
    if (picking === 'start') {
      setStart(p)
      setPicking(end ? null : 'end')
    } else if (picking === 'end') {
      setEnd(p)
      setPicking(null)
    } else if (picking === 'report') {
      setReportPoint(p)
      setPicking(null)
    } else if (picking === 'help') {
      setHelpFrom(p)
      setPicking(null)
    }
  }

  const useMine = async (which: 'start' | 'end' | 'help') => {
    setLocating(which)
    setLocError(null)
    try {
      const p = await getMyLocation()
      if (which === 'start') setStart(p)
      else if (which === 'end') setEnd(p)
      else setHelpFrom(p)
    } catch (e) {
      setLocError((e as Error).message)
    } finally {
      setLocating(null)
    }
  }

  const clearRoute = () => {
    setStart(null)
    setEnd(null)
    setPicking(null)
    setRoute(null)
    setRouteError(null)
  }

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
  const namedPoints = useMemo<NamedPoint[]>(() => {
    if (!data) return []
    const pts: NamedPoint[] = []
    const c = data.source.area?.center
    if (c) pts.push({ label: 'IIIT Guwahati (campus centre)', point: { lat: c[0], lon: c[1] } })
    data.places
      .filter((p) => p.in_demo_area && p.name)
      .sort((a, b) => placeName(a).localeCompare(placeName(b)))
      .forEach((p) => pts.push({ label: `${placeName(p)} · ${categoryMeta(p.category).label}`, point: { lat: p.lat, lon: p.lon } }))
    return pts
  }, [data])
  const selectedPlace = selection?.kind === 'place' ? data?.places.find((p) => p.id === selection.id) : undefined
  const tonight = `${todayIST()}T23:30`
  const afterReport = () => setRefresh((n) => n + 1)

  const toggle = (cat: string) =>
    setHidden((h) => {
      const n = new Set(h)
      if (n.has(cat)) n.delete(cat)
      else n.add(cat)
      return n
    })

  const pickHint =
    picking === 'start' ? 'Tap the map to set the start (A)'
      : picking === 'end' ? 'Tap the map to set the destination (B)'
        : picking === 'report' ? 'Tap the street you are reporting'
          : picking === 'help' ? 'Tap where you are'
            : null

  return (
    <div className="mx-auto max-w-[1600px] space-y-3 sm:space-y-4">
      <header className="flex flex-col gap-3 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-beacon-400">Walker</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight sm:text-3xl">Plan a safer walk</h1>
        </div>
        {/* Time of the walk: open/closed is judged for this time, not for now */}
        <div className="-mx-4 flex items-center gap-2 overflow-x-auto px-4 sm:mx-0 sm:flex-wrap sm:px-0" role="group" aria-label="Time of walk">
          <span className="shrink-0 text-xs text-ink-400">Walk time (IST)</span>
          <button onClick={() => setAt(undefined)}
            className={`min-h-10 shrink-0 rounded-lg px-3 text-sm font-medium ${!at ? 'bg-beacon-400 text-ink-950' : 'bg-ink-800 text-ink-300 hover:bg-ink-700'}`}>
            Now
          </button>
          <button onClick={() => setAt(tonight)}
            className={`min-h-10 shrink-0 rounded-lg px-3 text-sm font-medium ${at === tonight ? 'bg-beacon-400 text-ink-950' : 'bg-ink-800 text-ink-300 hover:bg-ink-700'}`}>
            Tonight 11:30 pm
          </button>
          <input type="datetime-local" aria-label="Choose walk time" value={at ?? ''} onChange={(e) => setAt(e.target.value || undefined)}
            className="min-h-10 shrink-0 rounded-lg border border-ink-600 bg-ink-850 px-2 text-sm text-ink-100 [color-scheme:dark]" />
        </div>
      </header>

      {/* Category filters */}
      <div className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0" aria-label="Filter places">
        <button onClick={() => setOpenOnly((v) => !v)} aria-pressed={openOnly}
          className={`min-h-9 shrink-0 rounded-full px-3 text-sm font-medium ring-1 ring-inset ${openOnly ? 'bg-beacon-400 text-ink-950 ring-beacon-400' : 'text-ink-300 ring-ink-600 hover:bg-ink-800'}`}>
          Open at walk time only
        </button>
        <span className="mx-1 hidden w-px shrink-0 bg-ink-700 sm:block" />
        {CATEGORY_ORDER.map((cat) => {
          const n = counts[cat] ?? 0
          const on = !hidden.has(cat)
          return (
            <button key={cat} onClick={() => toggle(cat)} disabled={n === 0} aria-pressed={on && n > 0}
              className={`min-h-9 shrink-0 rounded-full px-3 text-sm ring-1 ring-inset disabled:cursor-not-allowed disabled:opacity-40 ${on ? 'bg-ink-700 text-ink-100 ring-ink-600' : 'text-ink-400 ring-ink-700 line-through'}`}>
              {categoryMeta(cat).plural} <span className="tabular-nums text-ink-400">{n}</span>
            </button>
          )
        })}
      </div>

      {map.error && !data ? (
        <ErrorState message={map.error} onRetry={map.reload} />
      ) : (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_420px]">
          <div className="relative h-[56vh] min-h-[340px] min-w-0 overflow-hidden rounded-2xl border border-ink-700 lg:h-[calc(100vh-220px)]">
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
                <MapView source={data.source} streets={data.streets} places={visiblePlaces} selection={selection} onSelect={setSelection}
                  picking={picking !== null} onPick={onPick} start={start} end={end} route={route}
                  helpRoute={tab === 'help' ? help?.best_open?.geometry ?? null : null}
                  reportPoint={tab === 'report' ? reportPoint : null} helpFrom={tab === 'help' ? helpFrom : null} />
                <div className="pointer-events-none absolute top-3 right-3 left-14 z-[500] flex">
                  <div className="rounded-lg bg-ink-950/90 px-3 py-1.5 text-xs text-ink-300 ring-1 ring-ink-700">
                    {pickHint ? (
                      <span className="font-semibold text-beacon-300">{pickHint}</span>
                    ) : (
                      <>Open/closed for <span className="font-semibold text-ink-100">{formatAt(data.at)}</span></>
                    )}
                    {map.loading && <span className="ml-2 text-beacon-300">updating…</span>}
                  </div>
                </div>
                {/* Big buttons for phones */}
                <div className="absolute right-3 bottom-8 z-[500] flex flex-col gap-2 lg:hidden">
                  <button onClick={() => showPanel('help')} className="min-h-12 rounded-full bg-beacon-400 px-4 text-sm font-semibold text-ink-950 shadow-lg">Help point</button>
                  <button onClick={() => showPanel('report')} className="min-h-12 rounded-full bg-ink-950/95 px-4 text-sm font-semibold text-ink-100 shadow-lg ring-1 ring-ink-600">Report</button>
                </div>
              </>
            )}
          </div>

          <aside ref={panelRef} className="min-w-0 scroll-mt-20 rounded-2xl border border-ink-700 bg-ink-850 p-4 sm:p-5 lg:h-[calc(100vh-220px)] lg:overflow-y-auto">
            {!data ? (
              <div className="space-y-3">
                <Skeleton className="h-5 w-2/5" />
                <Skeleton className="h-4 w-full" />
              </div>
            ) : selection?.kind === 'street' ? (
              <StreetInfo id={selection.id} at={at} refreshKey={String(refresh)} onClose={() => setSelection(null)} onPick={setSelection} />
            ) : selectedPlace ? (
              <PlaceInfo p={selectedPlace} onClose={() => setSelection(null)} onReported={afterReport} />
            ) : (
              <div className="space-y-5">
                <div role="tablist" aria-label="Walker tools" className="grid grid-cols-3 gap-1 rounded-xl bg-ink-900 p-1">
                  {(
                    [
                      ['route', 'Route'],
                      ['report', 'Report'],
                      ['help', 'Help point'],
                    ] as const
                  ).map(([t, label]) => (
                    <button key={t} role="tab" aria-selected={tab === t} onClick={() => { setTab(t); setPicking(null) }}
                      className={`min-h-10 rounded-lg text-sm font-medium ${tab === t ? 'bg-beacon-400 text-ink-950' : 'text-ink-300'}`}>
                      {label}
                    </button>
                  ))}
                </div>
                {locError && <ErrorState title="Location" message={locError} />}
                {tab === 'route' && (
                  <>
                    <RoutePanel start={start} end={end} picking={picking} setPicking={setPicking} onClear={clearRoute} route={route}
                      loading={routeLoading} error={routeError} onRetry={findRoute} places={namedPoints}
                      onSet={(w, p) => (w === 'start' ? setStart(p) : setEnd(p))} onMine={useMine}
                      locating={locating === 'start' || locating === 'end' ? locating : null} at={at} />
                    {!route && (
                      <div className="border-t border-ink-700 pt-5">
                        <AreaOverview data={data} onPick={setSelection} />
                      </div>
                    )}
                  </>
                )}
                {tab === 'report' && (
                  <ReportPanel point={reportPoint} picking={picking === 'report'} onPickOnMap={() => setPicking(picking === 'report' ? null : 'report')}
                    onSetPoint={setReportPoint} onSent={afterReport} at={at} />
                )}
                {tab === 'help' && (
                  <HelpPointPanel from={helpFrom} picking={picking === 'help'} onUseMine={() => useMine('help')}
                    onPickOnMap={() => setPicking(picking === 'help' ? null : 'help')} result={help} loading={helpLoading}
                    error={helpError} locating={locating === 'help'} />
                )}
              </div>
            )}
          </aside>
        </div>
      )}
    </div>
  )
}
