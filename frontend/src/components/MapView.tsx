// The map, drawn with MapLibre GL JS. The background map comes from the configured provider (lib/mapProvider.ts);
// ShadowMap's own data — streets coloured by safety score, safe places, routes — is drawn on top from our backend.
import 'maplibre-gl/dist/maplibre-gl.css'
import * as maplibregl from 'maplibre-gl'
import type { GeoJSONSource, LngLatBoundsLike, StyleSpecification } from 'maplibre-gl'
// MapLibre runs its heavy work in a background "worker" script. Tell it exactly where that file is,
// because the build tool moves MapLibre's main code and the default guess would point to the wrong place.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
import { useEffect, useRef, useState } from 'react'
import type { LatLon, MapSource, Place, RouteResult, Street } from '../api'
import { mapProvider } from '../lib/mapProvider'
import { ROAD_CLASS, SAFETY_COLOURS, categoryMeta, placeName } from '../lib/mapMeta'

maplibregl.setWorkerUrl(workerUrl)

export type Selection = { kind: 'street'; id: number } | { kind: 'place'; id: number } | null

// Used only if the provider's map cannot load (e.g. no internet): plain background, our data still drawn.
const FALLBACK_STYLE: StyleSpecification = {
  version: 8,
  sources: {},
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': '#0b1220' } }],
}
const STYLE_TIMEOUT_MS = 10000
// Our own streets and places come from OpenStreetMap too; this credit shows even when the background map is off.
const SHADOWMAP_DATA_CREDIT = 'Streets & places: © OpenStreetMap contributors'

type LineFeature = GeoJSON.Feature<GeoJSON.LineString, Record<string, unknown>>
const lonLat = (g: [number, number][]) => g.map(([lat, lon]) => [lon, lat])
const collection = (features: GeoJSON.Feature[]): GeoJSON.FeatureCollection => ({ type: 'FeatureCollection', features })

function streetFeatures(streets: Street[]): GeoJSON.FeatureCollection {
  return collection(
    streets.map(
      (s): LineFeature => ({
        type: 'Feature',
        id: s.id,
        geometry: { type: 'LineString', coordinates: lonLat(s.geometry) },
        properties: {
          id: s.id,
          name: s.name || 'Unnamed road',
          score: s.score,
          color: s.colour ? SAFETY_COLOURS[s.colour] : ROAD_CLASS[s.road_class].color,
          width: ROAD_CLASS[s.road_class].weight,
          dashed: s.road_class === 'lane' || s.road_class === 'underpass',
        },
      }),
    ),
  )
}

function lineFeature(g: [number, number][] | undefined): GeoJSON.FeatureCollection {
  return collection(g && g.length > 1 ? [{ type: 'Feature', geometry: { type: 'LineString', coordinates: lonLat(g) }, properties: {} }] : [])
}

function areaFeature(source: MapSource): GeoJSON.FeatureCollection {
  const b = source.area?.bbox
  if (!b) return collection([])
  const ring = [[b.west, b.south], [b.east, b.south], [b.east, b.north], [b.west, b.north], [b.west, b.south]]
  return collection([{ type: 'Feature', geometry: { type: 'LineString', coordinates: ring }, properties: {} }])
}

// Width grows with zoom: thin when zoomed out, as in the old map at zoom 15, wider when zoomed in.
const widthExpr = (extra = 0): maplibregl.ExpressionSpecification => [
  'interpolate', ['linear'], ['zoom'],
  12, ['*', ['+', ['get', 'width'], extra], 0.5],
  15, ['+', ['get', 'width'], extra],
  18, ['*', ['+', ['get', 'width'], extra], 2],
]

function addLayers(map: maplibregl.Map) {
  map.addSource('sm-area', { type: 'geojson', data: collection([]) })
  map.addSource('sm-streets', { type: 'geojson', data: collection([]) })
  map.addSource('sm-shortest', { type: 'geojson', data: collection([]) })
  map.addSource('sm-safest', { type: 'geojson', data: collection([]) })

  map.addLayer({ id: 'sm-area', type: 'line', source: 'sm-area', paint: { 'line-color': '#f5b83d', 'line-width': 1.5, 'line-opacity': 0.6, 'line-dasharray': [4, 4] } })
  map.addLayer({
    id: 'sm-street-halo', type: 'line', source: 'sm-streets', filter: ['==', ['get', 'id'], -1],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': '#ffffff', 'line-width': widthExpr(7), 'line-opacity': 0.9 },
  })
  map.addLayer({
    id: 'sm-streets', type: 'line', source: 'sm-streets', filter: ['!=', ['get', 'dashed'], true],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'color'], 'line-width': widthExpr(), 'line-opacity': 0.9 },
  })
  map.addLayer({
    id: 'sm-streets-dashed', type: 'line', source: 'sm-streets', filter: ['==', ['get', 'dashed'], true],
    paint: { 'line-color': ['get', 'color'], 'line-width': widthExpr(), 'line-opacity': 0.9, 'line-dasharray': [2, 2] },
  })
  map.addLayer({
    id: 'sm-shortest', type: 'line', source: 'sm-shortest', layout: { 'line-cap': 'round' },
    paint: { 'line-color': '#e6ebf3', 'line-width': 4, 'line-opacity': 0.95, 'line-dasharray': [0.5, 2.5] },
  })
  map.addLayer({ id: 'sm-safest-casing', type: 'line', source: 'sm-safest', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#070c16', 'line-width': 11, 'line-opacity': 0.85 } })
  map.addLayer({ id: 'sm-safest', type: 'line', source: 'sm-safest', layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#f5b83d', 'line-width': 6 } })
  // wide invisible line on top, so streets are easy to tap on a phone
  map.addLayer({ id: 'sm-streets-hit', type: 'line', source: 'sm-streets', paint: { 'line-color': '#000000', 'line-width': 18, 'line-opacity': 0.01 } })
}

function setData(map: maplibregl.Map, id: string, data: GeoJSON.FeatureCollection) {
  ;(map.getSource(id) as GeoJSONSource | undefined)?.setData(data)
}

function placeElement(p: Place, selected: boolean): HTMLElement {
  // Outer element is positioned by MapLibre; the inner one carries our styles (and may scale when selected).
  const outer = document.createElement('button')
  outer.type = 'button'
  outer.className = 'sm-marker'
  outer.title = placeName(p)
  outer.setAttribute('aria-label', `${placeName(p)} (${categoryMeta(p.category).label})`)
  const cls = ['sm-pin', `sm-${p.status}`, p.source === 'manual' ? 'sm-manual' : '', selected ? 'sm-selected' : ''].filter(Boolean).join(' ')
  outer.innerHTML = `<div class="${cls}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${categoryMeta(p.category).icon}</svg></div>`
  return outer
}

function endpointElement(label: 'A' | 'B'): HTMLElement {
  const el = document.createElement('div')
  el.innerHTML = `<div class="sm-endpoint">${label}</div>`
  return el
}

export function MapView({
  source,
  streets,
  places,
  selection,
  onSelect,
  picking,
  onPick,
  start,
  end,
  route,
}: {
  source: MapSource
  streets: Street[]
  places: Place[]
  selection: Selection
  onSelect: (s: Selection) => void
  picking: boolean // true while the user is choosing a start or destination point
  onPick: (p: LatLon) => void
  start: LatLon | null
  end: LatLon | null
  route: RouteResult | null
}) {
  const containerRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const [ready, setReady] = useState(0) // counts style loads; 0 = not loaded. Data is re-applied after each load.
  const [baseMapFailed, setBaseMapFailed] = useState(false)
  // Latest callbacks/flags for the map's event handlers, which are registered once.
  const live = useRef({ onSelect, onPick, picking })
  live.current = { onSelect, onPick, picking }

  // Create the map once.
  useEffect(() => {
    if (!containerRef.current) return
    const center = source.area?.center ?? [26.0804, 91.5605]
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: FALLBACK_STYLE, // replaced by the provider's style below once it has downloaded
      center: [center[1], center[0]],
      zoom: 15,
      attributionControl: { compact: true, customAttribution: [mapProvider.attribution, SHADOWMAP_DATA_CREDIT].filter(Boolean) },
      dragRotate: false,
      pitchWithRotate: false,
    })
    map.touchZoomRotate.disableRotation()
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-left')
    mapRef.current = map
    if (import.meta.env.DEV) (window as unknown as { __shadowmapMap?: maplibregl.Map }).__shadowmapMap = map // for browser tests only

    map.on('style.load', () => {
      if (!map.getSource('sm-streets')) addLayers(map)
      setReady((n) => n + 1)
    })
    map.on('error', (e) => console.warn('[ShadowMap map]', e.error?.message ?? e)) // e.g. one missing tile; not fatal

    // Download the provider's style ourselves, so a failure is detected clearly and the map keeps working without it.
    const controller = new AbortController()
    let closed = false // set when this map is removed, so its own cancelled download is not reported as a failure
    const timer = setTimeout(() => controller.abort(), STYLE_TIMEOUT_MS)
    fetch(mapProvider.styleUrl, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((style: StyleSpecification) => map.setStyle(style, { diff: false }))
      .catch((err) => {
        if (closed) return
        console.warn('[ShadowMap map] background map unavailable:', err)
        setBaseMapFailed(true)
      })
      .finally(() => clearTimeout(timer))

    const tooltip = new maplibregl.Popup({ closeButton: false, closeOnClick: false, className: 'sm-tooltip', offset: 12 })
    map.on('mousemove', 'sm-streets-hit', (e) => {
      map.getCanvas().style.cursor = live.current.picking ? 'crosshair' : 'pointer'
      const f = e.features?.[0]
      if (!f || live.current.picking) return tooltip.remove()
      const score = f.properties.score
      tooltip.setLngLat(e.lngLat).setText(`${f.properties.name}${score != null && score !== 'null' ? ` · ${Math.round(Number(score))}` : ''}`).addTo(map)
    })
    map.on('mouseleave', 'sm-streets-hit', () => {
      map.getCanvas().style.cursor = live.current.picking ? 'crosshair' : ''
      tooltip.remove()
    })
    map.on('click', (e) => {
      const { picking: isPicking, onPick: pick, onSelect: select } = live.current
      if (isPicking) return pick({ lat: e.lngLat.lat, lon: e.lngLat.lng })
      const hit = map.queryRenderedFeatures(e.point, { layers: ['sm-streets-hit'] })[0]
      if (hit) select({ kind: 'street', id: Number(hit.properties.id) })
    })

    const resize = new ResizeObserver(() => map.resize())
    resize.observe(containerRef.current)
    return () => {
      closed = true
      controller.abort()
      resize.disconnect()
      map.remove()
      mapRef.current = null
    }
    // The map is created once; data changes are applied by the effects below.
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Fit to the demo area once the area is known.
  const b = source.area?.bbox
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready || !b) return
    setData(map, 'sm-area', areaFeature(source))
    map.fitBounds([[b.west, b.south], [b.east, b.north]] as LngLatBoundsLike, { padding: 12, duration: 0 })
  }, [ready, b?.south, b?.west, b?.north, b?.east]) // eslint-disable-line react-hooks/exhaustive-deps

  // Streets (re-sent whenever scores change, e.g. after new photos or reports).
  useEffect(() => {
    if (mapRef.current && ready) setData(mapRef.current, 'sm-streets', streetFeatures(streets))
  }, [ready, streets])

  // Selected street halo.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    map.setFilter('sm-street-halo', ['==', ['get', 'id'], selection?.kind === 'street' ? selection.id : -1])
  }, [ready, selection])

  // Routes; streets fade while a route is shown so it stands out.
  useEffect(() => {
    const map = mapRef.current
    if (!map || !ready) return
    setData(map, 'sm-safest', lineFeature(route?.safest.geometry))
    setData(map, 'sm-shortest', lineFeature(route && !route.same_route ? route.shortest.geometry : undefined))
    for (const id of ['sm-streets', 'sm-streets-dashed']) map.setPaintProperty(id, 'line-opacity', route ? 0.35 : 0.9)
  }, [ready, route])

  // Crosshair while choosing a point.
  useEffect(() => {
    if (mapRef.current) mapRef.current.getCanvas().style.cursor = picking ? 'crosshair' : ''
  }, [picking])

  // Place markers.
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const markers = places.map((p) => {
      const selected = selection?.kind === 'place' && selection.id === p.id
      const el = placeElement(p, selected)
      el.style.zIndex = selected ? '3' : p.status === 'open' ? '2' : '1'
      el.addEventListener('click', (ev) => {
        ev.stopPropagation()
        if (live.current.picking) live.current.onPick({ lat: p.lat, lon: p.lon })
        else live.current.onSelect({ kind: 'place', id: p.id })
      })
      return new maplibregl.Marker({ element: el }).setLngLat([p.lon, p.lat]).addTo(map)
    })
    return () => markers.forEach((m) => m.remove())
  }, [places, selection])

  // Bring a selected place into view.
  useEffect(() => {
    const map = mapRef.current
    if (!map || selection?.kind !== 'place') return
    const p = places.find((x) => x.id === selection.id)
    if (p && !map.getBounds().contains([p.lon, p.lat])) map.easeTo({ center: [p.lon, p.lat] })
  }, [selection]) // eslint-disable-line react-hooks/exhaustive-deps

  // Start (A) and destination (B).
  useEffect(() => {
    const map = mapRef.current
    if (!map) return
    const ms: maplibregl.Marker[] = []
    if (start) ms.push(new maplibregl.Marker({ element: endpointElement('A') }).setLngLat([start.lon, start.lat]).addTo(map))
    if (end) ms.push(new maplibregl.Marker({ element: endpointElement('B') }).setLngLat([end.lon, end.lat]).addTo(map))
    return () => ms.forEach((m) => m.remove())
  }, [start, end])

  return (
    <div className="relative h-full w-full">
      <div ref={containerRef} className="h-full w-full" data-testid="map" data-ready={ready > 0 ? 'yes' : 'no'} />
      {baseMapFailed && (
        <div className="pointer-events-none absolute right-3 bottom-8 z-10 max-w-[260px] rounded-lg bg-ink-950/90 px-3 py-2 text-xs text-ink-300 ring-1 ring-ink-700">
          Background map unavailable (no connection to {mapProvider.name}). ShadowMap streets, places and routes are still shown.
        </div>
      )}
    </div>
  )
}
