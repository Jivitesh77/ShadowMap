// Live Sentinel: phone camera + GPS, one photo every few seconds while moving (blueprint §5).
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { CameraIcon } from './Icons'
import { ErrorState } from './States'
import { Badge } from './Ui'

export const SENTINEL_LABELS = ['Zomato Rider #01', 'Swiggy Rider #01', 'Rapido #02', 'Uber #01', 'Volunteer #01']
const PHOTO_WIDTH = 640
const MIN_SPEED_KMH = 5
const MIN_DISTANCE_M = 30
const MAX_ACCURACY_M = 50
const MAX_QUEUE = 20

type LogEntry = { time: string; kind: 'ok' | 'skip' | 'fail'; text: string }

function distanceM(a: GeolocationCoordinates, b: GeolocationCoordinates) {
  const R = 6371000
  const toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b.latitude - a.latitude)
  const dLon = toRad(b.longitude - a.longitude)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a.latitude)) * Math.cos(toRad(b.latitude)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

function deviceId(): string {
  try {
    let id = localStorage.getItem('sm-device-id')
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem('sm-device-id', id)
    }
    return id
  } catch {
    return 'session-' + Math.random().toString(36).slice(2, 12)
  }
}

function isNight(d = new Date()) {
  const h = d.getHours()
  return h >= 18 || h < 6
}

function cameraError(err: unknown): string {
  const name = (err as DOMException)?.name
  if (name === 'NotAllowedError') return 'Camera permission was refused. Allow the camera for this site in your browser settings, then press Start again.'
  if (name === 'NotFoundError') return 'No camera was found on this device.'
  if (name === 'NotReadableError') return 'The camera is being used by another app. Close it and try again.'
  return 'The camera could not be opened.'
}

function gpsError(err: GeolocationPositionError): string {
  if (err.code === err.PERMISSION_DENIED) return 'Location permission was refused. Allow location for this site in your browser settings, then press Start again.'
  if (err.code === err.POSITION_UNAVAILABLE) return 'Your position is not available. Turn on location/GPS on the phone.'
  return 'Getting your position took too long. Move to open sky and try again.'
}

export function LiveSentinel() {
  const [label, setLabel] = useState(SENTINEL_LABELS[0])
  const [interval, setIntervalS] = useState(7)
  const [requireMoving, setRequireMoving] = useState(true)
  const [nightOnly, setNightOnly] = useState(true)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [pos, setPos] = useState<GeolocationPosition | null>(null)
  const [speedKmh, setSpeedKmh] = useState<number | null>(null)
  const [waiting, setWaiting] = useState<string | null>(null)
  const [counts, setCounts] = useState({ captured: 0, uploaded: 0, skipped: 0, failed: 0 })
  const [queueLen, setQueueLen] = useState(0)
  const [log, setLog] = useState<LogEntry[]>([])

  const videoRef = useRef<HTMLVideoElement>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const watchRef = useRef<number | null>(null)
  const timerRef = useRef<number | null>(null)
  const wakeRef = useRef<{ release: () => Promise<void> } | null>(null)
  const posRef = useRef<GeolocationPosition | null>(null)
  const prevPosRef = useRef<GeolocationPosition | null>(null)
  const speedRef = useRef<number | null>(null) // km/h: from the phone, or worked out from the last two positions
  const lastShotRef = useRef<GeolocationCoordinates | null>(null)
  const queueRef = useRef<{ blob: Blob; p: GeolocationPosition; speed: number | null; tries: number }[]>([])
  const uploadingRef = useRef(false)
  const settings = useRef({ label, interval, requireMoving, nightOnly })
  settings.current = { label, interval, requireMoving, nightOnly }

  const addLog = (kind: LogEntry['kind'], text: string) =>
    setLog((l) => [{ time: new Date().toLocaleTimeString('en-IN'), kind, text }, ...l].slice(0, 8))

  const pump = useCallback(async () => {
    if (uploadingRef.current) return
    uploadingRef.current = true
    while (queueRef.current.length) {
      const item = queueRef.current[0]
      const form = new FormData()
      form.append('image', item.blob, 'photo.jpg')
      form.append('lat', String(item.p.coords.latitude))
      form.append('lon', String(item.p.coords.longitude))
      form.append('accuracy_m', String(item.p.coords.accuracy))
      form.append('sentinel_label', settings.current.label)
      form.append('device_id', deviceId())
      form.append('captured_at', new Date(item.p.timestamp).toISOString())
      if (item.p.coords.heading != null && !Number.isNaN(item.p.coords.heading)) form.append('heading_deg', String(item.p.coords.heading))
      if (item.speed != null) form.append('speed_kmh', String(item.speed.toFixed(1)))
      try {
        const r = await api.livePhoto(form)
        queueRef.current.shift()
        setCounts((c) => ({ ...c, uploaded: c.uploaded + 1 }))
        addLog('ok', `Saved on ${r.street_name} (${r.snap_distance_m} m from your GPS point)`)
      } catch (err) {
        const e = err as ApiError
        if (e.status && e.status >= 400 && e.status < 500) {
          queueRef.current.shift() // the server refused this photo for a clear reason: do not retry
          setCounts((c) => ({ ...c, skipped: c.skipped + 1 }))
          addLog('skip', e.message)
        } else if (item.tries >= 2) {
          queueRef.current.shift()
          setCounts((c) => ({ ...c, failed: c.failed + 1 }))
          addLog('fail', `Upload failed after 3 tries: ${e.message}`)
        } else {
          item.tries += 1
          addLog('fail', `Upload failed, retrying: ${e.message}`)
          await new Promise((r) => setTimeout(r, 2000 * item.tries))
        }
      }
      setQueueLen(queueRef.current.length)
    }
    uploadingRef.current = false
  }, [])

  const tick = useCallback(() => {
    const p = posRef.current
    const s = settings.current
    const video = videoRef.current
    if (!p || !video || video.readyState < 2) return setWaiting('Waiting for camera and GPS…')
    if (s.nightOnly && !isNight()) return setWaiting('Paused: Sentinel Mode only captures between 6 pm and 6 am.')
    if (p.coords.accuracy > MAX_ACCURACY_M) return setWaiting(`Paused: GPS accuracy is ${Math.round(p.coords.accuracy)} m (needs ${MAX_ACCURACY_M} m).`)
    const speed = speedRef.current
    if (s.requireMoving && (speed ?? 0) < MIN_SPEED_KMH)
      return setWaiting(speed == null ? 'Paused: waiting for the phone to report speed (start moving).' : `Paused: moving at ${speed.toFixed(0)} km/h (needs ${MIN_SPEED_KMH}).`)
    if (lastShotRef.current && distanceM(lastShotRef.current, p.coords) < MIN_DISTANCE_M)
      return setWaiting(`Paused: less than ${MIN_DISTANCE_M} m from the last photo.`)
    if (queueRef.current.length >= MAX_QUEUE) return setWaiting('Paused: upload queue is full (poor connection).')

    const canvas = document.createElement('canvas')
    const scale = Math.min(1, PHOTO_WIDTH / video.videoWidth)
    canvas.width = Math.round(video.videoWidth * scale)
    canvas.height = Math.round(video.videoHeight * scale)
    canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height)
    canvas.toBlob(
      (blob) => {
        if (!blob) return
        lastShotRef.current = p.coords
        queueRef.current.push({ blob, p, speed, tries: 0 })
        setQueueLen(queueRef.current.length)
        setCounts((c) => ({ ...c, captured: c.captured + 1 }))
        setWaiting(null)
        pump()
      },
      'image/jpeg',
      0.7,
    )
  }, [pump])

  const stop = useCallback(() => {
    if (timerRef.current) clearInterval(timerRef.current)
    if (watchRef.current != null) navigator.geolocation.clearWatch(watchRef.current)
    streamRef.current?.getTracks().forEach((t) => t.stop())
    wakeRef.current?.release().catch(() => {})
    timerRef.current = watchRef.current = null
    streamRef.current = wakeRef.current = null
    setRunning(false)
    setWaiting(null)
  }, [])

  const start = async () => {
    setError(null)
    if (!window.isSecureContext) return setError('Camera and GPS only work on a secure (https) page. Open ShadowMap through its https address.')
    if (!navigator.mediaDevices?.getUserMedia) return setError('This browser cannot use the camera.')
    if (!('geolocation' in navigator)) return setError('This browser cannot read your location.')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }, audio: false })
      streamRef.current = stream
      if (videoRef.current) {
        videoRef.current.srcObject = stream
        await videoRef.current.play().catch(() => {})
      }
    } catch (err) {
      return setError(cameraError(err))
    }
    watchRef.current = navigator.geolocation.watchPosition(
      (p) => {
        const prev = prevPosRef.current
        let speed = p.coords.speed != null && !Number.isNaN(p.coords.speed) ? p.coords.speed * 3.6 : null
        if (speed == null && prev) {
          const dt = (p.timestamp - prev.timestamp) / 1000
          if (dt > 0) speed = (distanceM(prev.coords, p.coords) / dt) * 3.6
        }
        prevPosRef.current = p
        posRef.current = p
        speedRef.current = speed
        setPos(p)
        setSpeedKmh(speed)
      },
      (err) => {
        setError(gpsError(err))
        stop()
      },
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 20000 },
    )
    try {
      wakeRef.current = await (navigator as unknown as { wakeLock?: { request: (t: string) => Promise<{ release: () => Promise<void> }> } }).wakeLock?.request('screen') ?? null
    } catch {
      /* screen may still turn off; not fatal */
    }
    timerRef.current = window.setInterval(tick, settings.current.interval * 1000)
    setRunning(true)
  }

  // Restart the timer when the interval changes while running.
  useEffect(() => {
    if (!running) return
    if (timerRef.current) clearInterval(timerRef.current)
    timerRef.current = window.setInterval(tick, interval * 1000)
  }, [interval, running, tick])

  useEffect(() => stop, [stop])

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div className="space-y-4 rounded-2xl border border-ink-700 bg-ink-850 p-5">
        <div className="relative aspect-video overflow-hidden rounded-xl bg-ink-950">
          <video ref={videoRef} playsInline muted className="h-full w-full object-cover" />
          {!running && (
            <div className="absolute inset-0 grid place-items-center text-sm text-ink-400">
              <span className="flex items-center gap-2"><CameraIcon size={18} /> Camera off</span>
            </div>
          )}
          {running && <span className="absolute top-2 left-2"><Badge tone="bad">● Sentinel Mode on</Badge></span>}
        </div>
        {error && <ErrorState title="Cannot start Sentinel Mode" message={error} />}
        <button
          onClick={running ? stop : start}
          className={`flex w-full items-center justify-center gap-2 rounded-xl px-4 py-3 font-semibold ${running ? 'bg-danger text-white' : 'bg-beacon-400 text-ink-950'}`}
        >
          <CameraIcon size={18} /> {running ? 'Stop Sentinel Mode' : 'Start Sentinel Mode'}
        </button>
        <dl className="grid grid-cols-4 gap-2 text-center">
          {(['captured', 'uploaded', 'skipped', 'failed'] as const).map((k) => (
            <div key={k} className="rounded-lg bg-ink-900/60 p-2">
              <dd className="text-xl font-semibold tabular-nums">{counts[k]}</dd>
              <dt className="text-[11px] capitalize text-ink-400">{k}</dt>
            </div>
          ))}
        </dl>
        <p className="text-xs text-ink-400" role="status">
          {running
            ? waiting ?? 'Capturing.'
            : 'Nothing is captured until you press Start. Point the camera at the road, not at people or into homes.'}
          {queueLen > 0 && ` · ${queueLen} waiting to upload`}
        </p>
      </div>

      <div className="space-y-4 rounded-2xl border border-ink-700 bg-ink-850 p-5">
        <label className="block text-sm">
          <span className="text-ink-400">Sentinel name (pseudonym)</span>
          <select value={label} onChange={(e) => setLabel(e.target.value)} disabled={running}
            className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 text-ink-100">
            {SENTINEL_LABELS.map((l) => <option key={l}>{l}</option>)}
          </select>
          <span className="mt-1 block text-xs text-ink-400">Partner names are simulated for the demo; no company is involved.</span>
        </label>
        <label className="block text-sm">
          <span className="text-ink-400">Photo every {interval} seconds</span>
          <input type="range" min={5} max={10} value={interval} onChange={(e) => setIntervalS(Number(e.target.value))} className="mt-2 w-full accent-[#f5b83d]" />
        </label>
        <div className="space-y-2 text-sm">
          <label className="flex items-center gap-2"><input type="checkbox" checked={requireMoving} onChange={(e) => setRequireMoving(e.target.checked)} /> Only while moving (above {MIN_SPEED_KMH} km/h)</label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={nightOnly} onChange={(e) => setNightOnly(e.target.checked)} /> Only 6 pm – 6 am</label>
          <p className="text-xs text-ink-400">Turn these off only for testing on foot or in daytime. Photos within {MIN_DISTANCE_M} m of the last one are always skipped.</p>
        </div>
        <dl className="divide-y divide-ink-700 text-sm">
          <div className="flex justify-between py-1.5"><dt className="text-ink-400">GPS</dt><dd>{pos ? `${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}` : '—'}</dd></div>
          <div className="flex justify-between py-1.5"><dt className="text-ink-400">Accuracy</dt><dd>{pos ? `${Math.round(pos.coords.accuracy)} m` : '—'}</dd></div>
          <div className="flex justify-between py-1.5"><dt className="text-ink-400">Speed</dt><dd>{speedKmh != null ? `${speedKmh.toFixed(0)} km/h` : '—'}</dd></div>
        </dl>
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Recent</h3>
          {log.length === 0 ? (
            <p className="mt-1 text-sm text-ink-400">No photos yet.</p>
          ) : (
            <ul className="mt-1 space-y-1 text-xs">
              {log.map((l, i) => (
                <li key={i} className={l.kind === 'ok' ? 'text-ink-100' : l.kind === 'skip' ? 'text-ink-300' : 'text-danger'}>
                  <span className="text-ink-400">{l.time}</span> {l.text}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  )
}
