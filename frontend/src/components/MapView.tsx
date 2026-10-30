// The Leaflet map: OpenStreetMap tiles, streets drawn by road class, safe places as markers.
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect, useMemo } from 'react'
import { MapContainer, Marker, Polyline, Rectangle, TileLayer, Tooltip, useMap } from 'react-leaflet'
import type { MapSource, Place, Street } from '../api'
import { ROAD_CLASS, categoryMeta, placeName } from '../lib/mapMeta'

export type Selection = { kind: 'street'; id: number } | { kind: 'place'; id: number } | null

function placeIcon(p: Place, selected: boolean) {
  const cls = ['sm-pin', `sm-${p.status}`, p.source === 'manual' ? 'sm-manual' : '', selected ? 'sm-selected' : '']
    .filter(Boolean)
    .join(' ')
  return L.divIcon({
    className: '',
    html: `<div class="${cls}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">${categoryMeta(p.category).icon}</svg></div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15],
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

export function MapView({
  source,
  streets,
  places,
  selection,
  onSelect,
}: {
  source: MapSource
  streets: Street[]
  places: Place[]
  selection: Selection
  onSelect: (s: Selection) => void
}) {
  const center = source.area?.center ?? [26.0804, 91.5605]
  const b = source.area?.bbox
  const focus = useMemo<[number, number] | null>(() => {
    if (selection?.kind !== 'place') return null
    const p = places.find((x) => x.id === selection.id)
    return p ? [p.lat, p.lon] : null
  }, [selection, places])

  // draw the selected street last so it sits on top
  const ordered = useMemo(() => {
    const sel = selection?.kind === 'street' ? selection.id : -1
    return [...streets].sort((a, c) => Number(a.id === sel) - Number(c.id === sel))
  }, [streets, selection])

  return (
    <MapContainer center={center} zoom={15} className="h-full w-full" zoomControl preferCanvas={false}>
      <TileLayer
        className="sm-tiles"
        url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
        maxZoom={19}
      />
      <FitArea source={source} />
      <FocusOn target={focus} />
      {b && (
        <Rectangle
          bounds={[[b.south, b.west], [b.north, b.east]]}
          pathOptions={{ color: '#f5b83d', weight: 1.5, opacity: 0.6, dashArray: '6 6', fill: false }}
          interactive={false}
        />
      )}
      {ordered.map((s) => {
        const style = ROAD_CLASS[s.road_class]
        const selected = selection?.kind === 'street' && selection.id === s.id
        return [
          <Polyline
            key={`${s.id}-${selected}`}
            positions={s.geometry}
            interactive={false}
            pathOptions={{
              color: selected ? '#f5b83d' : style.color,
              weight: selected ? style.weight + 3 : style.weight,
              opacity: selected ? 1 : 0.85,
              dashArray: style.dash,
              lineCap: 'round',
            }}
          />,
          // wide invisible line on top, so streets are easy to tap on a phone
          <Polyline
            key={`${s.id}-hit`}
            positions={s.geometry}
            pathOptions={{ color: '#000', opacity: 0, weight: 18 }}
            eventHandlers={{
              click: (e) => {
                L.DomEvent.stopPropagation(e)
                onSelect({ kind: 'street', id: s.id })
              },
            }}
          >
            <Tooltip sticky>{s.name || 'Unnamed road'}</Tooltip>
          </Polyline>,
        ]
      })}
      {places.map((p) => {
        const selected = selection?.kind === 'place' && selection.id === p.id
        return (
          <Marker
            key={`${p.id}-${p.status}-${selected}`}
            position={[p.lat, p.lon]}
            icon={placeIcon(p, selected)}
            zIndexOffset={selected ? 1000 : p.status === 'open' ? 500 : 0}
            eventHandlers={{ click: () => onSelect({ kind: 'place', id: p.id }) }}
            keyboard
            title={placeName(p)}
          />
        )
      })}
    </MapContainer>
  )
}
