// The ONLY place in the frontend that talks to the backend.
// Addresses are relative (/api/...): in development Vite forwards them to the backend on port 8000.

export interface Health {
  status: 'ok' | 'degraded'
  database: 'ok' | 'error'
  demo_mode: boolean
  gemini_configured: boolean
  server_time_utc: string
}

export interface Summary {
  streets: number
  places: number
  observations: number
  reports: number
  walks: number
  alerts: number
  active_walks: number
  open_alerts: number
}

export type RoadClass = 'main' | 'residential' | 'lane' | 'underpass'
export type PlaceStatus = 'open' | 'closed' | 'unknown'
export type StatusBasis = 'listed' | 'default' | 'missing' | 'unreadable'

export interface Street {
  id: number
  name: string | null
  road_type: string
  road_class: RoadClass
  lit: string | null
  length_m: number
  geometry: [number, number][]
  osm_way_id: number
}

export interface Place {
  id: number
  osm_id: string | null
  name: string | null
  category: string
  lat: number
  lon: number
  opening_hours: string | null
  phone: string | null
  status: PlaceStatus
  status_basis: StatusBasis
  source: 'openstreetmap' | 'manual'
  in_demo_area: boolean
  verified_by: string | null
  verified_on: string | null
  note: string | null
  distance_from_center_m: number | null
  distance_m?: number
}

export interface MapSource {
  file?: string
  downloaded_at_utc?: string
  osm_data_timestamp?: string
  licence?: string
  area?: {
    name: string
    center: [number, number]
    bbox: { south: number; west: number; north: number; east: number }
    help_radius_m: number
  }
}

export interface MapData {
  at: string
  source: MapSource
  streets: Street[]
  places: Place[]
}

export interface StreetDetail {
  id: number
  name: string | null
  road_type: string
  road_class: RoadClass
  lit: string | null
  length_m: number
  osm_way_id: number
  map_score: number | null
  observations: number
  reports: number
  nearby_places: Place[]
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 10000): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let res: Response
  try {
    res = await fetch(path, {
      ...init,
      signal: controller.signal,
      headers: { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw new ApiError('The server took too long to answer.')
    throw new ApiError('Cannot reach the ShadowMap server. Check that the backend is running.')
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) {
    let detail = `Server error (${res.status}).`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* body was not JSON */
    }
    // The dev proxy answers 500/502/504 when the backend is not running.
    if ([500, 502, 504].includes(res.status) && detail.startsWith('Server error')) {
      detail = 'Cannot reach the ShadowMap server. Check that the backend is running.'
    }
    throw new ApiError(detail, res.status)
  }
  return res.json() as Promise<T>
}

export const api = {
  health: () => request<Health>('/api/health', undefined, 4000),
  summary: () => request<Summary>('/api/summary'),
  map: (at?: string) => request<MapData>(`/api/map${at ? `?at=${encodeURIComponent(at)}` : ''}`),
  street: (id: number, at?: string) =>
    request<StreetDetail>(`/api/streets/${id}${at ? `?at=${encodeURIComponent(at)}` : ''}`),
}
