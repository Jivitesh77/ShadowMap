// Small Leaflet map for tracing a ride: tap points in order; the path follows mapped streets.
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, useMap, useMapEvents } from 'react-leaflet'
import type { MapData } from '../api'
import { tileProvider, tileReferrerPolicy } from '../lib/mapProvider'

function pointIcon(n: number) {
  return L.divIcon({ className: '', html: `<div class="sm-endpoint">${n}</div>`, iconSize: [28, 28], iconAnchor: [14, 14] })
}

function Fit({ data }: { data: MapData }) {
  const map = useMap()
  const b = data.source.area?.bbox
  useEffect(() => {
    if (b) map.fitBounds([[b.south, b.west], [b.north, b.east]], { padding: [8, 8] })
  }, [map, b?.south, b?.west, b?.north, b?.east])
  return null
}

function Clicks({ onAdd }: { onAdd: (p: [number, number]) => void }) {
  useMapEvents({ click: (e) => onAdd([e.latlng.lat, e.latlng.lng]) })
  return null
}

export function TraceMap({
  data,
  points,
  path,
  onAdd,
}: {
  data: MapData
  points: [number, number][]
  path: [number, number][] | null
  onAdd: (p: [number, number]) => void
}) {
  return (
    <MapContainer center={data.source.area?.center ?? [26.0804, 91.5605]} zoom={15} className="h-full w-full sm-picking">
      <TileLayer className="sm-tiles" url={tileProvider.url} attribution={tileProvider.attribution} maxZoom={19} referrerPolicy={tileReferrerPolicy} />
      <Fit data={data} />
      <Clicks onAdd={onAdd} />
      {data.streets.map((s) => (
        <Polyline key={s.id} positions={s.geometry} interactive={false} pathOptions={{ color: '#a3a7c2', weight: 3, opacity: 0.8 }} />
      ))}
      {path && (
        <>
          <Polyline positions={path} interactive={false} pathOptions={{ color: '#ffffff', weight: 10, opacity: 0.95 }} />
          <Polyline positions={path} interactive={false} pathOptions={{ color: '#5a5fc8', weight: 5 }} />
        </>
      )}
      {points.map((p, i) => (
        <Marker key={`${i}-${p[0]}-${p[1]}`} position={p} icon={pointIcon(i + 1)} interactive={false} />
      ))}
    </MapContainer>
  )
}
