// The Leaflet map: OpenStreetMap tiles, streets coloured by safety score, safe places, routes.
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import { MapContainer, Marker, Polyline, Rectangle, TileLayer, Tooltip, useMap, useMapEvents } from 'react-leaflet'
import type { LatLon, MapSource, Place, RouteResult, Street } from '../api'
import { ROAD_CLASS, SAFETY_COLOURS, categoryMeta, formatAge, placeName, ROUTE_COLOURS } from '../lib/mapMeta'
import { tileProvider } from '../lib/mapProvider'

export type Selection = { kind: 'street'; id: number } | { kind: 'place'; id: number } | null

function placeIcon(p: Place, selected: boolean) {
  const cls = ['sm-pin', `sm-${p.status}`, p.sources.includes('shadowmap') ? 'sm-manual' : '', selected ? 'sm-selected' : '']
    .filter(Boolean)
    .join(' ')
  return L.divIcon({
    className: '',
    html: `<div class="${cls}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${categoryMeta(p.category).icon}</svg></div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
  })
}

function endpointIcon(label: 'A' | 'B' | 'R' | 'H') {
  return L.divIcon({
    className: '',
    html: `<div class="sm-endpoint">${label}</div>`,
    iconSize: [28, 28],
    iconAnchor: [14, 14],
  })
}

function FitArea({ source }: { source: MapSource }) {
  const map = useMap()
  const b = source.area?.bbox
  useEffect(() => {
    if (b) map.fitBounds([[b.south, b.west], [b.north, b.east]], { padding: [12, 12] })
  }, [map, b?.south, b?.west, b?.north, b?.east])
  return null
}

function FocusOn({ target }: { target: [number, number] | null }) {
  const map = useMap()
  useEffect(() => {
    if (target && !map.getBounds().pad(-0.1).contains(target)) map.panTo(target)
  }, [map, target])
  return null
}

function ExposeForTests() {
  const map = useMap()
  useEffect(() => {
    if (import.meta.env.DEV) (window as unknown as { __shadowmapMap?: L.Map }).__shadowmapMap = map // browser tests only
  }, [map])
  return null
}

function ClickToPick({ onPick }: { onPick?: (p: LatLon) => void }) {
  useMapEvents({ click: (e) => onPick?.({ lat: e.latlng.lat, lon: e.latlng.lng }) })
  return null
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
  helpRoute = null,
  reportPoint = null,
  helpFrom = null,
  walkRoute = null,
  me = null,
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
  helpRoute?: [number, number][] | null
  reportPoint?: LatLon | null
  helpFrom?: LatLon | null
  walkRoute?: [number, number][] | null
  me?: LatLon | null
}) {
  const center = source.area?.center ?? [26.0804, 91.5605]
  const b = source.area?.bbox
  const focus = useMemo<[number, number] | null>(() => {
    if (selection?.kind === 'street') {
      const s = streets.find((x) => x.id === selection.id)
      return s ? (s.geometry[Math.floor(s.geometry.length / 2)] as [number, number]) : null
    }
    if (selection?.kind !== 'place') return null
    const p = places.find((x) => x.id === selection.id)
    return p ? [p.lat, p.lon] : null
  }, [selection, places, streets])

  // draw the selected street last so it sits on top
  const ordered = useMemo(() => {
    const sel = selection?.kind === 'street' ? selection.id : -1
    return [...streets].sort((a, c) => Number(a.id === sel) - Number(c.id === sel))
  }, [streets, selection])

  const dim = !!route // fade streets while routes are shown, so the routes stand out

  return (
    // preferCanvas: one canvas instead of thousands of SVG paths, so dense cities (Delhi: ~6,000 street pieces) stay smooth
    <MapContainer center={center} zoom={15} className={`h-full w-full ${picking ? 'sm-picking' : ''}`} zoomControl preferCanvas>
      <TileLayer
        className="sm-tiles"
        url={tileProvider.url}
        attribution={tileProvider.attribution}
        maxZoom={19}
      />
      <FitArea source={source} />
      <ExposeForTests />
      <FocusOn target={focus} />
      <ClickToPick onPick={picking ? onPick : undefined} />
      {b && (
        <Rectangle
          bounds={[[b.south, b.west], [b.north, b.east]]}
          pathOptions={{ color: ROUTE_COLOURS.safest, weight: 1.5, opacity: 0.55, dashArray: '6 6', fill: false }}
          interactive={false}
        />
      )}
      {ordered.map((s) => {
        const style = ROAD_CLASS[s.road_class]
        const selected = selection?.kind === 'street' && selection.id === s.id
        const color = s.colour ? SAFETY_COLOURS[s.colour] : style.color
        return [
          selected && (
            <Polyline
              key={`${s.id}-halo`}
              positions={s.geometry}
              interactive={false}
              pathOptions={{ color: ROUTE_COLOURS.safest, weight: style.weight + 7, opacity: 0.35, lineCap: 'round' }}
            />
          ),
          <Polyline
            key={`${s.id}-${selected}-${color}-${dim}`}
            positions={s.geometry}
            interactive={false}
            pathOptions={{
              color,
              weight: selected ? style.weight + 2 : style.weight,
              opacity: dim ? 0.35 : 0.9,
              dashArray: style.dash,
              lineCap: 'round',
            }}
          />,
          // wide invisible line on top, so streets are easy to tap on a phone
          <Polyline
            key={`${s.id}-hit-${picking}`}
            positions={s.geometry}
            pathOptions={{ color: '#000', opacity: 0, weight: 18 }}
            eventHandlers={{
              click: (e) => {
                L.DomEvent.stopPropagation(e)
                if (picking) onPick({ lat: e.latlng.lat, lon: e.latlng.lng })
                else onSelect({ kind: 'street', id: s.id })
              },
            }}
          >
            {!picking && (
              <Tooltip sticky>{`${s.name || 'Unnamed road'}${s.score != null ? ` · ${Math.round(s.score)}` : ''} · ${formatAge(s.freshest_photo_age_min)}`}</Tooltip>
            )}
          </Polyline>,
        ]
      })}

      {route && (
        <>
          {!route.same_route && (
            <Polyline
              positions={route.shortest.geometry}
              interactive={false}
              pathOptions={{ color: ROUTE_COLOURS.shortest, weight: 4, opacity: 0.95, dashArray: '2 9', lineCap: 'round' }}
            />
          )}
          <Polyline positions={route.safest.geometry} interactive={false} pathOptions={{ color: ROUTE_COLOURS.halo, weight: 11, opacity: 0.95 }} />
          <Polyline
            positions={route.safest.geometry}
            interactive={false}
            pathOptions={{ color: ROUTE_COLOURS.safest, weight: 6, opacity: 1, lineCap: 'round', lineJoin: 'round' }}
          />
        </>
      )}

      {places.map((p) => {
        const selected = selection?.kind === 'place' && selection.id === p.id
        return (
          <Marker
            key={`${p.id}-${p.status}-${selected}-${picking}`}
            position={[p.lat, p.lon]}
            icon={placeIcon(p, selected)}
            zIndexOffset={selected ? 1000 : p.status === 'open' ? 500 : 0}
            eventHandlers={{
              click: () => (picking ? onPick({ lat: p.lat, lon: p.lon }) : onSelect({ kind: 'place', id: p.id })),
            }}
            keyboard
            title={placeName(p)}
          />
        )
      })}
      {helpRoute && helpRoute.length > 1 && (
        <>
          <Polyline positions={helpRoute} interactive={false} pathOptions={{ color: ROUTE_COLOURS.halo, weight: 10, opacity: 0.95 }} />
          <Polyline positions={helpRoute} interactive={false} pathOptions={{ color: ROUTE_COLOURS.help, weight: 5, dashArray: '8 6', lineCap: 'round' }} />
        </>
      )}
      {walkRoute && walkRoute.length > 1 && (
        <>
          <Polyline positions={walkRoute} interactive={false} pathOptions={{ color: ROUTE_COLOURS.halo, weight: 11, opacity: 0.95 }} />
          <Polyline positions={walkRoute} interactive={false} pathOptions={{ color: ROUTE_COLOURS.walk, weight: 6, lineCap: 'round' }} />
        </>
      )}
      {me && (
        <Marker position={[me.lat, me.lon]} icon={L.divIcon({ className: '', html: '<div class="sm-live-dot"></div>', iconSize: [22, 22], iconAnchor: [11, 11] })}
          zIndexOffset={3000} interactive={false} />
      )}
      {reportPoint && <Marker position={[reportPoint.lat, reportPoint.lon]} icon={endpointIcon('R')} zIndexOffset={2000} interactive={false} />}
      {helpFrom && <Marker position={[helpFrom.lat, helpFrom.lon]} icon={endpointIcon('H')} zIndexOffset={2000} interactive={false} />}
      {start && <Marker position={[start.lat, start.lon]} icon={endpointIcon('A')} zIndexOffset={2000} interactive={false} />}
      {end && <Marker position={[end.lat, end.lon]} icon={endpointIcon('B')} zIndexOffset={2000} interactive={false} />}
    </MapContainer>
  )
}
