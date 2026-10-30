// A small Leaflet map for the contact and police screens: planned route, live position, where the walker last moved, destination.
import 'leaflet/dist/leaflet.css'
import L from 'leaflet'
import { useEffect } from 'react'
import { MapContainer, Marker, Polyline, TileLayer, Tooltip, useMap } from 'react-leaflet'
import { tileProvider } from '../lib/mapProvider'

const dot = (cls: string, label = '') =>
  L.divIcon({ className: '', html: `<div class="${cls}">${label}</div>`, iconSize: [24, 24], iconAnchor: [12, 12] })

function Follow({ target, route }: { target: [number, number] | null; route: [number, number][] | null }) {
  const map = useMap()
  useEffect(() => {
    if (route && route.length > 1) map.fitBounds(L.latLngBounds(route).pad(0.3), { animate: false })
  }, [map, route?.length]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (target && !map.getBounds().pad(-0.15).contains(target)) map.panTo(target)
  }, [map, target?.[0], target?.[1]]) // eslint-disable-line react-hooks/exhaustive-deps
  return null
}

export function LiveMap({
  route,
  live,
  lastMoved,
  dest,
  alertAt,
}: {
  route: [number, number][] | null
  live: [number, number] | null
  lastMoved?: [number, number] | null
  dest?: [number, number] | null
  alertAt?: [number, number] | null
}) {
  const center = live ?? route?.[0] ?? dest ?? [26.0804, 91.5605]
  return (
    <MapContainer center={center} zoom={16} className="h-full w-full">
      <TileLayer className="sm-tiles" url={tileProvider.url} attribution={tileProvider.attribution} maxZoom={19} />
      <Follow target={live} route={route} />
      {route && (
        <>
          <Polyline positions={route} interactive={false} pathOptions={{ color: '#ffffff', weight: 10, opacity: 0.95 }} />
          <Polyline positions={route} interactive={false} pathOptions={{ color: '#5a5fc8', weight: 5 }} />
        </>
      )}
      {dest && <Marker position={dest} icon={dot('sm-endpoint', 'B')}><Tooltip>Destination</Tooltip></Marker>}
      {alertAt && <Marker position={alertAt} icon={dot('sm-alert-dot')}><Tooltip>Where the alert was raised</Tooltip></Marker>}
      {lastMoved && <Marker position={lastMoved} icon={dot('sm-moved-dot')}><Tooltip>Last seen moving</Tooltip></Marker>}
      {live && <Marker position={live} icon={dot('sm-live-dot')} zIndexOffset={1000}><Tooltip>Live position</Tooltip></Marker>}
    </MapContainer>
  )
}
