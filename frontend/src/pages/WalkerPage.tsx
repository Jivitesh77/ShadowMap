import { useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import { api, type HelpPointResult, type LatLon, type MapData, type MapScores, type RouteResult } from '../api'
import { useApi } from '../hooks/useApi'
import { getMyLocation } from '../lib/location'
import { TopBarSlotContext } from '../components/AppShell'
import { AlertIcon, ChevronRightIcon, InfoIcon, MapPinIcon, ShareIcon, UsersIcon } from '../components/Icons'
import { HelpPointPanel } from '../components/HelpPointPanel'
import { AreaOverview, PlaceInfo, StreetInfo } from '../components/MapPanels'
import { MapView, type Selection } from '../components/MapView'
import { PlaceSearch } from '../components/PlaceSearch'
import { PlanBar, type ChosenPoint } from '../components/PlanBar'
import { ReportPanel } from '../components/ReportPanel'
import { RoutePanel, type NamedPoint, type PickTarget } from '../components/RoutePanel'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { WalkActive, WalkSetup } from '../components/WalkWithMe'
import { walkSession, type WalkSession } from '../lib/walkSession'
import { tabKeys } from '../lib/tabKeys'
import { CATEGORY_ORDER, ROUTE_COLOURS, SAFETY_COLOURS, categoryMeta, formatDistance, placeName } from '../lib/mapMeta'

type Tab = 'route' | 'report' | 'help' | 'area'
const TABS: readonly Tab[] = ['route', 'report', 'help', 'area']

/** Today's date in India time, as YYYY-MM-DD. */
function todayIST(): string {
  return new Date(Date.now() + 5.5 * 3600_000).toISOString().slice(0, 10)
}

function formatAt(at: string): string {
  const d = new Date(`${at}:00`)
  return d.toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
}

/** Street shapes and place details (loaded once) with the newest scores and open / closed status merged in. */
function withLiveScores(base: MapData | null, live: MapScores | null): MapData | null {
  if (!base || !live || (base.source.city && live.city !== base.source.city)) return base
  const streets = new Map(live.streets.map((s) => [s.id, s]))
  const places = new Map(live.places.map((p) => [p.id, p]))
  return {
    ...base,
    at: live.at,
    generated_utc: live.generated_utc,
    streets: base.streets.map((s) => ({ ...s, ...streets.get(s.id) })),
    places: base.places.map((p) => ({ ...p, ...places.get(p.id) })),
  }
}

// Categories with more places than this start hidden (Delhi has ~900 shops); tapping the chip shows them.
const BUSY_CATEGORY = 60

export default function WalkerPage() {
  const [at, setAt] = useState<string | undefined>(undefined) // undefined = now
  const [refresh, setRefresh] = useState(0) // bumped after a report so scores, routes and panels reload
  // Shapes and details once (Delhi ~3 MB); afterwards only the light scores view, every minute or when time / reports change.
  const base = useApi(() => api.map(), undefined, 'base')
  const live = useApi(() => (base.data ? api.mapScores(at) : Promise.resolve(null)), at ? undefined : 60000,
    `${at ?? 'now'}|${refresh}|${base.data ? 'ready' : 'waiting'}`)
  const merged = useMemo(() => withLiveScores(base.data, live.data), [base.data, live.data])
  const map = {
    data: merged,
    error: base.error ?? (live.error && !live.data ? live.error : null),
    loading: base.loading || live.loading,
    reload: () => { base.reload(); live.reload() },
  }
  const [hidden, setHidden] = useState<Set<string>>(new Set())
  const busyHiddenFor = useRef<string | null>(null)
  const [openOnly, setOpenOnly] = useState(false)
  const [selection, setSelection] = useState<Selection>(null)
  const [tab, setTab] = useState<Tab>('route')
  const [picking, setPicking] = useState<PickTarget>(null)
  const panelRef = useRef<HTMLElement>(null)

  // Walk With Me
  const walkCfg = useApi(api.walkConfig)
  const [session, setSession] = useState<WalkSession | null>(() => walkSession.get())
  const [setupOpen, setSetupOpen] = useState(false)
  const [me, setMe] = useState<LatLon | null>(null)
  const [walkRoute, setWalkRoute] = useState<[number, number][] | null>(null)
  useEffect(() => {
    if (!session) return setWalkRoute(null)
    api.walkState(session.walk_id, session.token).then((s) => setWalkRoute(s.route)).catch(() => {})
  }, [session])
  const onWalkPosition = useCallback((p: LatLon) => setMe(p), [])
  const onWalkFinished = useCallback(() => {
    setSession(null)
    setMe(null)
  }, [])

  // Route planning
  const [startPt, setStartPt] = useState<ChosenPoint | null>(null)
  const [endPt, setEndPt] = useState<ChosenPoint | null>(null)
  const start = startPt?.point ?? null
  const end = endPt?.point ?? null
  const setStart = (p: LatLon, label = 'Point on the map') => setStartPt({ point: p, label })
  const setEnd = (p: LatLon, label = 'Point on the map') => setEndPt({ point: p, label })
  const planRef = useRef<HTMLDivElement>(null)
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

  const countedFor = useRef<string | null>(null) // the start/destination pair already counted for the repair ranking
  const findRoute = useCallback(async () => {
    if (!start || !end) return
    const pair = `${start.lat},${start.lon}|${end.lat},${end.lon}`
    const count = countedFor.current !== pair // later re-plans (time changed, report sent) are not new routes
    setRouteLoading(true)
    setRouteError(null)
    try {
      setRoute(await api.route(start, end, at, count))
      if (count) countedFor.current = pair
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
      if (which === 'start') setStart(p, 'My location')
      else if (which === 'end') setEnd(p, 'My location')
      else setHelpFrom(p)
    } catch (e) {
      setLocError((e as Error).message)
    } finally {
      setLocating(null)
    }
  }

  const clearRoute = () => {
    setStartPt(null)
    setEndPt(null)
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
  // Busy categories start hidden once per city (the person's own choices are kept after that).
  useEffect(() => {
    if (!data) return
    const city = data.source.city ?? 'default'
    if (busyHiddenFor.current === city) return
    busyHiddenFor.current = city
    setHidden(new Set(CATEGORY_ORDER.filter((c) => (counts[c] ?? 0) > BUSY_CATEGORY)))
  }, [data, counts])
  const busyHidden = CATEGORY_ORDER.filter((c) => hidden.has(c) && (counts[c] ?? 0) > BUSY_CATEGORY)
  const visiblePlaces = useMemo(
    () => (data?.places ?? []).filter((p) => !hidden.has(p.category) && (!openOnly || p.status === 'open')),
    [data, hidden, openOnly],
  )
  const namedPoints = useMemo<NamedPoint[]>(() => {
    if (!data) return []
    const pts: NamedPoint[] = []
    const c = data.source.area?.center
    if (c) pts.push({ label: data.source.centre_label ?? 'Area centre', point: { lat: c[0], lon: c[1] } })
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

  const slot = useContext(TopBarSlotContext)
  const showFound = (r: { kind: 'place' | 'street'; id: number }) => {
    if (r.kind === 'place') {
      const cat = data?.places.find((p) => p.id === r.id)?.category
      if (cat && hidden.has(cat)) toggle(cat) // make sure the marker is visible
      setOpenOnly(false)
    }
    setSelection(r)
    if (window.innerWidth < 1024) setTimeout(() => panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }
  const goTo = (p: { lat: number; lon: number; label: string }) => {
    setEnd({ lat: p.lat, lon: p.lon }, p.label)
    setTab('route')
    setSelection(null)
    if (!start) setPicking(null)
  }
  const compare = () => {
    setTab('route')
    setSelection(null)
    setSetupOpen(false)
    if (!route || routeError) findRoute() // the route is planned automatically once both points are set: never twice
    if (window.innerWidth < 1024) setTimeout(() => panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
  }
  const shareJourney = () => {
    if (route && start && end) {
      setSelection(null)
      setSetupOpen(true)
      if (window.innerWidth < 1024) setTimeout(() => panelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 50)
    } else {
      planRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    }
  }
  const areaKm = data ? data.streets.reduce((t, x) => t + x.length_m, 0) / 1000 : 0
  const travelInfo = route
    ? `Suggested: ${route.safest.duration_min} min · ${formatDistance(route.safest.distance_m)} · ${route.safest.red_m} m on red streets`
    : data
      ? `${data.streets.length} street pieces (${areaKm.toFixed(0)} km) · ${data.places.length} places · OSM ${data.source.osm_data_timestamp ? new Date(data.source.osm_data_timestamp).toLocaleDateString('en-IN', { dateStyle: 'medium' }) : 'data'}`
      : 'Loading map data…'

  const pickHint =
    picking === 'start' ? 'Tap the map to set the start (A)'
      : picking === 'end' ? 'Tap the map to set the destination (B)'
        : picking === 'report' ? 'Tap the street you are reporting'
          : picking === 'help' ? 'Tap where you are'
            : null

  return (
    <div className="mx-auto max-w-[1600px] space-y-5">
      {slot && data && createPortal(
        <PlaceSearch places={data.places} streets={data.streets} areaName={data.source.area?.name ?? 'this area'} onShow={showFound} onGo={goTo} />,
        slot,
      )}

      <header>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-beacon-400">Walker</p>
        <h1 className="mt-1 text-2xl font-bold tracking-tight sm:text-4xl">Plan a safer way home.</h1>
        <p className="mt-1.5 text-sm text-ink-300 sm:text-base">Compare street conditions before you leave.</p>
      </header>

      <div ref={planRef} className="scroll-mt-24">
        <PlanBar start={startPt} end={endPt} places={namedPoints} picking={picking} setPicking={setPicking}
          onSet={(w, p) => (w === 'start' ? setStartPt(p) : setEndPt(p))} onMine={useMine}
          locating={locating === 'start' || locating === 'end' ? locating : null}
          at={at} setAt={setAt} tonight={tonight} onCompare={compare} canCompare={!!(start && end)} loading={routeLoading} onClear={clearRoute} />
        {locError && <div className="mt-3"><ErrorState title="Location" message={locError} /></div>}
      </div>

      {map.error && !data ? (
        <ErrorState message={map.error} onRetry={map.reload} />
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_400px]">
          <section className="sm-card flex min-w-0 flex-col p-3 sm:p-4 lg:h-[min(76vh,760px)]" aria-label="Route map">
            <div className="flex flex-wrap items-center justify-between gap-2 px-1 pb-3">
              <h2 className="font-semibold text-ink-100">Route map</h2>
              {data && (
                <p className="flex items-baseline gap-2 text-xs text-ink-400">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${map.loading ? 'bg-caution' : 'bg-safe'}`} />
                  <span>
                    {data.source.area?.name ?? 'Demo area'} · open/closed for <span className="font-medium text-ink-100">{formatAt(data.at)}</span>
                    {data.generated_utc && <> · scores updated {new Date(data.generated_utc).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' })}</>}
                    {live.error && live.data && <span className="text-caution-ink"> · could not refresh, showing the last scores</span>}
                  </span>
                </p>
              )}
            </div>
            {/* Category filters */}
            <div className="sm-no-scrollbar -mx-3 flex gap-2 overflow-x-auto px-3 pb-3 sm:-mx-4 sm:px-4" aria-label="Filter places">
              <button onClick={() => setOpenOnly((v) => !v)} aria-pressed={openOnly}
                className={`min-h-8 shrink-0 rounded-full px-3 text-xs font-medium ring-1 ring-inset ${openOnly ? 'bg-beacon-400 text-white ring-beacon-400' : 'text-ink-300 ring-ink-600 hover:bg-ink-900'}`}>
                Open at walk time only
              </button>
              {CATEGORY_ORDER.map((cat) => {
                const n = counts[cat] ?? 0
                const on = !hidden.has(cat)
                return (
                  <button key={cat} onClick={() => toggle(cat)} disabled={n === 0} aria-pressed={on && n > 0}
                    className={`min-h-8 shrink-0 rounded-full px-3 text-xs ring-1 ring-inset disabled:cursor-not-allowed disabled:opacity-40 ${on ? 'bg-lavender-50 text-ink-100 ring-lavender-200' : 'text-ink-400 ring-ink-700 line-through'}`}>
                    {categoryMeta(cat).plural} <span className="tabular-nums text-ink-400">{n}</span>
                  </button>
                )
              })}
            </div>
            {busyHidden.length > 0 && (
              <p className="-mt-1 px-1 pb-2 text-[11px] text-ink-400">
                {busyHidden.map((c) => categoryMeta(c).plural).join(', ')} hidden to keep the map readable — tap a crossed-out chip to show them.
                Help points and the Area tab still list every place.
              </p>
            )}
            <div className="relative h-[56vh] min-h-[340px] overflow-hidden rounded-xl border border-ink-700 lg:h-auto lg:min-h-0 lg:flex-1">
              {!data ? (
                <Skeleton className="h-full w-full rounded-none" />
              ) : data.streets.length === 0 ? (
                <div className="grid h-full place-items-center bg-ink-900 p-6">
                  <EmptyState icon={<MapPinIcon size={22} />} title="No map data in the database">
                    Run the map build step (see README) to load the saved OpenStreetMap data.
                  </EmptyState>
                </div>
              ) : (
                <>
                  <MapView source={data.source} streets={data.streets} places={visiblePlaces} selection={selection} onSelect={setSelection}
                    picking={picking !== null} onPick={onPick} start={start} end={end} route={route}
                    helpRoute={tab === 'help' ? help?.best_open?.geometry ?? null : null}
                    reportPoint={tab === 'report' ? reportPoint : null} helpFrom={tab === 'help' ? helpFrom : null}
                    walkRoute={session ? walkRoute : null} me={session ? me : null} />
                  {(pickHint || map.loading) && (
                    <div className="pointer-events-none absolute top-3 right-3 left-14 z-[500] flex">
                      <div className="rounded-lg bg-ink-950/95 px-3 py-1.5 text-xs text-ink-300 shadow-sm ring-1 ring-ink-700">
                        {pickHint && <span className="font-semibold text-beacon-300">{pickHint}</span>}
                        {map.loading && <span className={pickHint ? 'ml-2' : ''}>updating…</span>}
                      </div>
                    </div>
                  )}
                  {/* Legend */}
                  <div className="pointer-events-none absolute bottom-6 left-3 z-[500] hidden flex-wrap items-center gap-x-4 gap-y-1 rounded-xl bg-ink-950/95 px-3 py-2 text-[11px] text-ink-300 shadow-sm ring-1 ring-ink-700 sm:flex">
                    {route && (
                      <>
                        <span className="inline-flex items-center gap-1.5"><span className="h-1 w-5 rounded-full" style={{ background: ROUTE_COLOURS.safest }} />Suggested route</span>
                        {!route.same_route && <span className="inline-flex items-center gap-1.5"><span className="h-0 w-5 border-t-2 border-dotted" style={{ borderColor: ROUTE_COLOURS.shortest }} />Shortest route</span>}
                      </>
                    )}
                    <span className="inline-flex items-center gap-1.5">Streets:
                      {(['green', 'yellow', 'red'] as const).map((c) => <span key={c} className="h-1 w-3 rounded-full" style={{ background: SAFETY_COLOURS[c] }} />)}
                      score
                    </span>
                  </div>
                  {/* Big buttons for phones */}
                  <div className="absolute right-3 bottom-8 z-[500] flex flex-col gap-2 lg:hidden">
                    <button onClick={() => showPanel('help')} className="min-h-12 rounded-full bg-beacon-400 px-4 text-sm font-semibold text-white shadow-lg">Help point</button>
                  </div>
                </>
              )}
            </div>
          </section>

          <aside ref={panelRef} className="sm-card min-w-0 scroll-mt-24 p-4 sm:p-5 lg:h-[min(76vh,760px)] lg:overflow-y-auto">
            {!data ? (
              <div className="space-y-3">
                <Skeleton className="h-5 w-2/5" />
                <Skeleton className="h-4 w-full" />
              </div>
            ) : session && walkCfg.data ? (
              <WalkActive session={session} config={walkCfg.data} at={at} onPosition={onWalkPosition} onFinished={onWalkFinished} />
            ) : setupOpen && start && end && walkCfg.data ? (
              <WalkSetup start={start} end={end} config={walkCfg.data} onCancel={() => setSetupOpen(false)}
                onStarted={(s) => { setSetupOpen(false); setSession(s) }} />
            ) : selection?.kind === 'street' ? (
              <StreetInfo id={selection.id} at={at} refreshKey={String(refresh)} onClose={() => setSelection(null)} onPick={setSelection} />
            ) : selectedPlace ? (
              <PlaceInfo p={selectedPlace} centreLabel={data?.source.centre_label} onClose={() => setSelection(null)} onReported={afterReport} />
            ) : (
              <div className="space-y-5">
                <div role="tablist" aria-label="Walker tools" className="grid grid-cols-4 gap-1 rounded-xl bg-ink-900 p-1"
                  onKeyDown={tabKeys(TABS, tab, (t) => { setTab(t); setPicking(null) })}>
                  {(
                    [
                      ['route', 'Routes'],
                      ['report', 'Report'],
                      ['help', 'Help'],
                      ['area', 'Area'],
                    ] as const
                  ).map(([t, label]) => (
                    <button key={t} role="tab" aria-selected={tab === t} tabIndex={tab === t ? 0 : -1} onClick={() => { setTab(t); setPicking(null) }}
                      className={`min-h-9 rounded-lg text-sm font-medium transition-colors ${tab === t ? 'bg-ink-850 text-ink-100 shadow-sm ring-1 ring-ink-700' : 'text-ink-400 hover:text-ink-100'}`}>
                      {label}
                    </button>
                  ))}
                </div>
                {tab === 'route' && (
                  <>
                    <RoutePanel start={start} end={end} route={route} loading={routeLoading} error={routeError} onRetry={findRoute} at={at} />
                    {route && start && end && (
                      <button onClick={() => setSetupOpen(true)} className="min-h-12 w-full rounded-xl bg-beacon-400 font-semibold text-white hover:bg-beacon-500">
                        Start Walk With Me
                      </button>
                    )}
                    <button onClick={() => showPanel('help')}
                      className="flex min-h-12 w-full items-center justify-center gap-2 rounded-xl bg-danger/10 font-semibold text-danger ring-1 ring-danger/20 hover:bg-danger/15">
                      <AlertIcon size={18} /> Nearest help point
                    </button>
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
                {tab === 'area' && <AreaOverview data={data} onPick={setSelection} />}
              </div>
            )}
          </aside>
        </div>
      )}

      {/* Shortcuts */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-5">
        <Shortcut icon={<ShareIcon size={20} />} title="Share your journey" onClick={shareJourney}
          text={session ? 'Walk With Me is running — see the panel above' : route ? 'Let a trusted contact follow your walk live' : 'Plan a route first, then let a trusted contact follow it'} />
        <Shortcut icon={<UsersIcon size={20} />} title="Report a concern" onClick={() => showPanel('report')}
          text="Dark street, broken light, a place closed — keeps local information up to date" />
        <Shortcut icon={<InfoIcon size={20} />} title="Travel information" onClick={() => showPanel(route ? 'route' : 'area')} text={travelInfo} />
      </div>
    </div>
  )
}

function Shortcut({ icon, title, text, onClick }: { icon: ReactNode; title: string; text: string; onClick: () => void }) {
  return (
    <button onClick={onClick} className="sm-card group flex min-h-20 items-center gap-4 p-4 text-left transition-shadow hover:shadow-md">
      <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-lavender-50 text-beacon-300">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold text-ink-100">{title}</span>
        <span className="block text-xs text-ink-400">{text}</span>
      </span>
      <ChevronRightIcon size={18} className="shrink-0 text-ink-400 transition-transform group-hover:translate-x-0.5" />
    </button>
  )
}
