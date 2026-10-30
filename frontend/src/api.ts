// The ONLY place in the frontend that talks to the backend.
import { currentCity, withCity } from './lib/city'
import { isAccessRefusal } from './lib/accessCodes'
import { accessHeaders, setAccessCode } from './lib/sentinelAccess'

// Backend address. Empty in development (Vite forwards /api to port 8000). In production set VITE_API_BASE,
// e.g. https://shadowmap-backend.onrender.com, and allow the frontend's address in the backend's CORS_ORIGINS.
export const API_BASE = (import.meta.env.VITE_API_BASE ?? '').replace(/\/$/, '')
// Addresses are relative (/api/...): in development Vite forwards them to the backend on port 8000.

export interface Health {
  status: 'ok' | 'degraded'
  database: 'ok' | 'error'
  demo_mode: boolean
  gemini_configured: boolean
  server_time_utc: string
}

export interface CityInfo {
  id: string
  name: string
  center: [number, number] | null
  bbox: { south: number; west: number; north: number; east: number } | null
  has_map_data: boolean
}

export interface CitiesInfo {
  default: string
  cities: CityInfo[]
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
export type StatusBasis = 'listed' | 'missing' | 'unreadable' | 'community'

export interface Street {
  id: number
  name: string | null
  road_type: string
  road_class: RoadClass
  lit: string | null
  length_m: number
  geometry: [number, number][]
  osm_way_id: number
  score: number | null
  colour: SafetyColour | null
  map_score?: number
  photo_score?: number | null
  photo_weight?: number
  report_adjustment?: number
  freshest_photo_age_min?: number | null
}

export type SafetyColour = 'green' | 'yellow' | 'red'
export type PlaceSource = 'osm' | 'shadowmap'
export type Confidence = 'high' | 'medium' | 'low'

export interface LatLon {
  lat: number
  lon: number
}

export interface RouteSummary {
  distance_m: number
  duration_min: number
  metres_by_colour: Record<SafetyColour, number>
  red_m: number
  places_passed_not_closed: number
  places_passed: (Pick<Place, 'id' | 'name' | 'category' | 'status' | 'status_basis' | 'sources'> & { distance_m: number })[]
  freshest_photo_age_min: number | null
  segments: {
    street_id: number
    name: string | null
    road_class: RoadClass
    length_m: number
    score: number
    colour: SafetyColour
    freshest_photo_age_min: number | null
  }[]
  geometry: [number, number][]
}

export interface RouteResult {
  at: string
  start: { requested: LatLon; snapped: [number, number]; snap_distance_m: number }
  end: { requested: LatLon; snapped: [number, number]; snap_distance_m: number }
  shortest: RouteSummary
  safest: RouteSummary
  same_route: boolean
  safest_within_detour_limit: boolean
  max_detour_ratio: number
  notes: string[]
}

export interface Place {
  id: number
  osm_id: string | null
  name: string | null
  category: string
  lat: number
  lon: number
  opening_hours: string | null
  hours_source: PlaceSource | null
  phone: string | null
  status: PlaceStatus
  status_basis: StatusBasis
  sources: PlaceSource[]
  osm_last_edited: string | null
  duplicate_osm_ids: string[]
  in_demo_area: boolean
  verified_by: string | null
  verified_on: string | null
  note: string | null
  match_note: string | null
  confidence: Confidence
  confidence_reason: string
  community_report: { kind: 'place_closed' | 'place_open'; created_at_utc: string } | null
  distance_from_center_m: number | null
  distance_m?: number
}

export interface MapSource {
  city?: string
  centre_label?: string
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
  score: number | null
  colour: SafetyColour | null
  map_score?: number
  photo_score?: number | null
  photo_weight?: number
  report_adjustment?: number
  freshest_photo_age_min?: number | null
  observations: number
  reports: number
  nearby_places: Place[]
}

// Google Places results: shown only in a separate, attributed list. Never on the map, never stored.
export interface GooglePlace {
  place_id: string
  name: string | null
  address: string | null
  google_type: string | null
  category: string | null
  business_status: string | null
  google_maps_uri: string | null
  distance_m: number | null
}

export interface GoogleNearby {
  source: 'google'
  attribution: string
  radius_m: number
  results: GooglePlace[]
  notes: string[]
}

// ---- Walker: briefing, reports, help point, observations ----
export type Lang = 'en' | 'hi'
export interface Briefing {
  text: string
  sentences: string[]
  source: 'ai' | 'data'
  note: string | null
  lang: Lang
  model: string | null
}

export type ReportKind = 'broken_light' | 'dark' | 'deserted' | 'felt_unsafe' | 'well_lit' | 'place_closed' | 'place_open'
export interface ReportResult {
  report_id: number
  kind: ReportKind
  fades_at_utc: string | null
  street_id?: number
  street_name?: string
  effect_points?: number
  street_score_now?: number
  street_colour_now?: SafetyColour
  place_id?: number
  place_name?: string | null
}
export interface ActiveReport {
  id: number
  kind: ReportKind
  age_min: number
  fades_in_min: number | null
}

export interface HelpPlace {
  id: number
  name: string | null
  category: string
  status: PlaceStatus
  status_basis?: string
  walk_m?: number
  walk_min?: number
  straight_line_m?: number
  geometry?: [number, number][]
}
export interface HelpPointResult {
  at: string
  best_open: HelpPlace | null
  other_open: HelpPlace[]
  unknown_hours: HelpPlace[]
  outside_mapped_area: HelpPlace[]
  message: string | null
}

export interface StreetObservation {
  id: number
  captured_age_min: number
  sentinel_label: string
  source: 'live' | 'video'
  position_source: 'gps' | 'traced_route' | null
  analysis_status: string
  lighting: string | null
  streetlights_visible: number | null
  streetlights_working: number | null
  people: string | null
  open_places_count: number | null
  vehicles: string | null
  isolation: string | null
  hazards: string[] | null
  description: string | null
  confidence: string | null
  uncertainty: string | null
  photo_available: boolean
  photo_url: string | null
  photo_note: string
}

// ---- Walk With Me ----
export interface WalkTimers {
  stop_s: number
  off_route_m: number
  off_route_s: number
  late_s: number
  ask_s: number
  contacts_to_police_s: number
}
export interface WalkConfig {
  demo_mode: boolean
  timers: WalkTimers
  helplines: { emergency: string; women: string; police: string }
  demo_call_number: string | null
}
export interface WalkerState {
  walk_id: string
  status: 'active' | 'checking' | 'alert' | 'arrived' | 'ended' | 'expired'
  asking: boolean
  trigger: string | null
  check_started_utc: string | null
  escalation: number
  expected_arrival_utc: string | null
  route: [number, number][]
  dest: [number, number]
  last: [number, number]
  contacts: { name: string; phone: string | null }[]
  simulated: boolean
  timers: WalkTimers
  last_position_utc: string | null
  last_accuracy_m: number | null
  sharing: boolean
  pin_locked_until_utc: string | null
}
export interface WalkEvent {
  at: string
  kind: string
  text: string
}
export interface ContactView {
  walker_name: string
  status: WalkerState['status']
  duress: boolean
  escalation: number
  trigger: string | null
  started_utc: string
  expected_arrival_utc: string | null
  ended_utc: string | null
  route: [number, number][] | null
  dest: [number, number] | null
  last: [number, number] | null
  last_position_utc: string | null
  battery_pct: number | null
  simulated: boolean
  events: WalkEvent[]
  alerts: { level: string; trigger: string; status: string; created_utc: string }[]
}
export interface WhereAmI {
  street: string | null
  landmark: { name: string | null; category: string; distance_m: number } | null
  nearest_open: { name: string | null; category: string; distance_m: number } | null
  nearest_police: { name: string | null; distance_m: number; phone: string | null } | null
}
export interface PoliceAlert {
  id: number
  walk_id: string
  walker_name: string
  walker_phone: string | null
  trigger: string
  duress: boolean
  status: 'new' | 'acknowledged' | 'unit_sent' | 'resolved'
  created_utc: string
  updated_utc: string
  alert_position: [number, number] | null
  live_position: [number, number] | null
  live_position_utc: string | null
  last_moved: [number, number] | null
  last_moved_utc: string | null
  route: [number, number][] | null
  dest: [number, number] | null
  walk_status: string
  simulated_positions: boolean
  contacts: string[]
  history: { at: string; status: string; by: string }[]
  resolved_reason: string | null
}
export interface RepairItem {
  rank: number
  street_id: number
  name: string
  road_class: string
  length_m: number
  lat: number
  lon: number
  osm_way_id: number
  broken_light_reports: number
  independent_reporters: number
  dark_reports: number
  nights_dark_last_7: number
  walks_through: number
  routes_planned_through: number
  status: string
  latest_dark_utc: string | null
  evidence: { observation_id: number; captured_utc: string; sentinel: string; lighting: string | null; description: string | null; photo_available: boolean; photo_url: string | null }[]
}

// ---- Sentinel ----
export interface VideoInfo {
  duration_s: number
  codec: string | null
  width: number | null
  height: number | null
  rotation: number | string | null
  size_bytes: number
  format: string | null
  location_tag: string | null
  creation_time_utc: string | null
}

export interface CheckedVideo {
  video_ref: string
  name: string
  info: VideoInfo
}

export interface VideoJob {
  id: number
  city: string
  original_name: string
  source_kind: 'upload' | 'asset'
  sentinel_label: string
  status: 'queued' | 'processing' | 'done' | 'failed'
  stage: string | null
  frames_total: number | null
  frames_done: number
  duration_s: number | null
  frame_interval_s: number
  recorded_at_utc: string | null
  recorded_at_source: 'user' | 'video_metadata' | null
  route_geometry: [number, number][] | null
  route_length_m: number | null
  position_note: string
  streets_covered: { street_id: number; name: string; frames: number }[]
  analysis: Record<string, number>
  error: string | null
  created_at_utc: string
}

export interface LivePhotoResult {
  observation_id: number
  street_id: number
  street_name: string
  snap_distance_m: number
  analysis_status: string
}

export class ApiError extends Error {
  constructor(
    message: string,
    public status?: number,
    public code?: string,
  ) {
    super(message)
  }
}

async function request<T>(path: string, init?: RequestInit, timeoutMs = 10000, isForm = false): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let res: Response
  try {
    res = await fetch(API_BASE + path, {
      ...init,
      signal: controller.signal,
      headers: isForm ? init?.headers : { 'Content-Type': 'application/json', ...init?.headers },
    })
  } catch (err) {
    if ((err as Error).name === 'AbortError') throw new ApiError('The server took too long to answer.')
    throw new ApiError('Cannot reach the ShadowMap server. Check that the backend is running.')
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) {
    let detail = `Server error (${res.status}).`
    let code: string | undefined
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
      else if (typeof body?.detail?.message === 'string') detail = body.detail.message
      else if (Array.isArray(body?.detail)) detail = 'The request was not valid.'
      if (typeof body?.detail?.code === 'string') code = body.detail.code
    } catch {
      /* body was not JSON */
    }
    // The dev proxy answers 500/502/504 when the backend is not running.
    if ([500, 502, 504].includes(res.status) && detail.startsWith('Server error')) {
      detail = 'Cannot reach the ShadowMap server. Check that the backend is running.'
    }
    // A Sentinel code the server no longer accepts is forgotten, so the page asks for it again.
    if (path.startsWith('/api/sentinel/') && isAccessRefusal(res.status, code)) setAccessCode(null)
    throw new ApiError(detail, res.status, code)
  }
  return res.json() as Promise<T>
}

/** Sends a form (files + fields). The browser sets the right content type itself. */
async function requestForm<T>(path: string, form: FormData, timeoutMs = 30000): Promise<T> {
  return request<T>(path, { method: 'POST', body: form, headers: accessHeaders() }, timeoutMs, true)
}

/** Largest video the server accepts (backend MAX_VIDEO_UPLOAD_MB, agreed 250 MB). Used for the upload box text and
 *  for error messages only — the server enforces the limit. */
export const VIDEO_UPLOAD_LIMIT_MB = 250
const TOO_LARGE_MESSAGE = `This video is larger than ${VIDEO_UPLOAD_LIMIT_MB} MB, the most ShadowMap accepts. Trim it to the ride (or a shorter part of it) and upload that.`

/** Uploads a video with a progress callback (0..1). fetch() cannot report upload progress, so this uses XHR. */
function uploadVideo(file: File, onProgress: (f: number) => void): Promise<CheckedVideo> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open('POST', API_BASE + '/api/sentinel/videos/uploads')
    Object.entries(accessHeaders()).forEach(([k, v]) => xhr.setRequestHeader(k, v))
    xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(e.loaded / e.total)
    xhr.onload = () => {
      let body: any = null
      try {
        body = JSON.parse(xhr.responseText)
      } catch {
        /* not JSON */
      }
      if (isAccessRefusal(xhr.status, body?.detail?.code)) setAccessCode(null)
      if (xhr.status >= 200 && xhr.status < 300) resolve(body)
      else if (xhr.status === 413 && !body?.detail?.message) reject(new ApiError(TOO_LARGE_MESSAGE, 413, 'too_large')) // e.g. a proxy's own 413 page
      else reject(new ApiError(body?.detail?.message ?? `Upload failed (${xhr.status}).`, xhr.status, body?.detail?.code))
    }
    // The server may close the connection on an oversized video before the browser reads its answer.
    xhr.onerror = () =>
      reject(file.size > VIDEO_UPLOAD_LIMIT_MB * 1024 * 1024
        ? new ApiError(TOO_LARGE_MESSAGE, 413, 'too_large')
        : new ApiError('Upload failed: cannot reach the ShadowMap server.'))
    const form = new FormData()
    form.append('file', file)
    xhr.send(form)
  })
}

export const api = {
  health: () => request<Health>('/api/health', undefined, 4000),
  summary: () => request<Summary>(withCity('/api/summary')),
  cities: () => request<CitiesInfo>('/api/cities'),
  map: (at?: string) => request<MapData>(withCity(`/api/map${at ? `?at=${encodeURIComponent(at)}` : ''}`)),
  route: (start: LatLon, end: LatLon, at?: string) =>
    request<RouteResult>('/api/route', { method: 'POST', body: JSON.stringify({ start, end, at, city: currentCity() }) }, 20000),
  googleStatus: () => request<{ configured: boolean; attribution: string }>('/api/google-places/status'),
  googleNearby: (lat: number, lon: number, radius_m: number) =>
    request<GoogleNearby>('/api/google-places/nearby', { method: 'POST', body: JSON.stringify({ lat, lon, radius_m }) }, 15000),
  sentinelStatus: () =>
    request<{ observations_by_analysis: Record<string, number>; ai_configured: boolean; ai_note: string | null }>('/api/sentinel/status'),
  livePhoto: (form: FormData) => requestForm<LivePhotoResult>('/api/sentinel/photo', form, 20000),
  assetVideos: () =>
    request<{ folder: string; videos: { name: string; size_bytes: number; supported: boolean }[] }>('/api/sentinel/videos/assets', {
      headers: accessHeaders(),
    }),
  checkAssetVideo: (name: string) =>
    request<CheckedVideo>(`/api/sentinel/videos/assets/${encodeURIComponent(name)}`, { headers: accessHeaders() }, 60000),
  uploadVideo,
  traceRoute: (waypoints: [number, number][]) =>
    request<{ geometry: [number, number][]; length_m: number; streets: number }>('/api/sentinel/trace', {
      method: 'POST',
      body: JSON.stringify({ waypoints, city: currentCity() }),
      headers: accessHeaders(),
    }),
  createVideoJob: (body: {
    video_ref: string
    sentinel_label: string
    waypoints: [number, number][]
    recorded_at_ist?: string
    use_video_time?: boolean
    ride_start_s?: number | null
    ride_end_s?: number | null
    frame_interval_s?: number
  }) => request<VideoJob>('/api/sentinel/videos/jobs', { method: 'POST', body: JSON.stringify({ ...body, city: currentCity() }), headers: accessHeaders() }, 60000),
  // Video jobs belong to one city: the server lists, shows and deletes only the selected city's jobs.
  videoJobs: (city: string | undefined = currentCity()) =>
    request<{ city: string; jobs: VideoJob[] }>(withCity('/api/sentinel/videos/jobs', city), { headers: accessHeaders() }),
  videoJob: (id: number, city: string | undefined = currentCity()) =>
    request<VideoJob>(withCity(`/api/sentinel/videos/jobs/${id}`, city), { headers: accessHeaders() }),
  deleteVideoJob: (id: number, city: string | undefined = currentCity()) =>
    request<{ deleted_job: number; observations_removed: number }>(withCity(`/api/sentinel/videos/jobs/${id}`, city), {
      method: 'DELETE',
      headers: accessHeaders(),
    }),
  briefing: (start: LatLon, end: LatLon, lang: Lang, at?: string) =>
    request<Briefing>('/api/route/briefing', { method: 'POST', body: JSON.stringify({ start, end, at, lang, city: currentCity() }) }, 45000),
  report: (body: { kind: ReportKind; lat: number; lon: number; device_id: string; place_id?: number; at?: string }) =>
    request<ReportResult>('/api/reports', { method: 'POST', body: JSON.stringify({ ...body, city: currentCity() }) }),
  reports: (q: { street_id?: number; place_id?: number }) =>
    request<{ reports: ActiveReport[] }>(`/api/reports?${new URLSearchParams(Object.entries(q).map(([k, v]) => [k, String(v)]))}`),
  helpPoint: (p: LatLon, at?: string) =>
    request<HelpPointResult>('/api/help-point', { method: 'POST', body: JSON.stringify({ ...p, at, city: currentCity() }) }, 30000),
  streetObservations: (id: number) => request<{ observations: StreetObservation[] }>(`/api/streets/${id}/observations`),
  walkConfig: () => request<WalkConfig>('/api/walks/config'),
  startWalk: (body: {
    walker_name: string
    walker_phone?: string
    contacts: { name: string; phone?: string }[]
    pin: string
    duress_pin?: string
    start: LatLon
    end: LatLon
    simulated: boolean
  }) => request<{ walk_id: string; walker_token: string; contact_path: string; expected_arrival_utc: string }>('/api/walks', { method: 'POST', body: JSON.stringify({ ...body, city: currentCity() }) }, 30000),
  walkState: (id: string, token: string) => request<WalkerState>(`/api/walks/${id}/state`, { headers: { 'X-Walk-Token': token } }),
  walkPosition: (id: string, token: string, p: LatLon & { battery_pct?: number; accuracy_m?: number }) =>
    request<WalkerState>(`/api/walks/${id}/position`, { method: 'POST', body: JSON.stringify(p), headers: { 'X-Walk-Token': token } }),
  walkSafe: (id: string, token: string, pin: string) =>
    request<WalkerState & { ok: boolean }>(`/api/walks/${id}/safe`, { method: 'POST', body: JSON.stringify({ pin }), headers: { 'X-Walk-Token': token } }),
  walkSos: (id: string, token: string) => request<{ ok: boolean }>(`/api/walks/${id}/sos`, { method: 'POST', headers: { 'X-Walk-Token': token } }),
  walkEnd: (id: string, token: string, pin: string, revoke = false) =>
    request<{ ok: boolean }>(`/api/walks/${id}/end`, { method: 'POST', body: JSON.stringify({ pin, revoke }), headers: { 'X-Walk-Token': token } }),
  walkNote: (id: string, token: string, target: '112' | '181' | 'police' | 'contact' | 'fake') =>
    request<{ ok: boolean }>(`/api/walks/${id}/note`, { method: 'POST', body: JSON.stringify({ kind: 'calling', target }), headers: { 'X-Walk-Token': token } }),
  contactView: (id: string) => request<ContactView>(`/api/walks/${id}/contact`),
  whereAmI: (p: LatLon, at?: string) => request<WhereAmI>('/api/where-am-i', { method: 'POST', body: JSON.stringify({ ...p, at, city: currentCity() }) }),
  policeAlerts: (code: string, scope: 'active' | 'history') =>
    request<{ simulated: boolean; alerts: PoliceAlert[] }>(withCity(`/api/police/alerts?scope=${scope}`), { headers: { 'X-Police-Token': code } }),
  policeStatus: (code: string, id: number, status: 'acknowledged' | 'unit_sent' | 'resolved') =>
    request<PoliceAlert>(withCity(`/api/police/alerts/${id}/status`), { method: 'POST', body: JSON.stringify({ status }), headers: { 'X-Police-Token': code } }),
  policeCoverage: (code: string) =>
    request<{ streets_seen_last_hour: number; streets_in_area: number }>(withCity('/api/police/coverage'), { headers: { 'X-Police-Token': code } }),
  cityRepairs: () => request<{ generated_utc: string; items: RepairItem[]; hotspots: RepairItem[]; note: string }>(withCity('/api/city/repairs')),
  street: (id: number, at?: string) =>
    request<StreetDetail>(`/api/streets/${id}${at ? `?at=${encodeURIComponent(at)}` : ''}`),
}
