// Video mode: turn a recorded night ride into street observations (blueprint §5).
// Frame positions come from the route traced here, never from invented GPS.
import { useEffect, useState } from 'react'
import { api, ApiError, VIDEO_UPLOAD_LIMIT_MB, type CheckedVideo, type VideoJob } from '../api'
import { useApi } from '../hooks/useApi'
import { currentCity } from '../lib/city'
import { formatDistance } from '../lib/mapMeta'
import { SENTINEL_LABELS } from './LiveSentinel'
import { EmptyState, ErrorState, LoadingBlock, Skeleton } from './States'
import { TraceMap } from './TraceMap'
import { Badge } from './Ui'
import { CameraIcon } from './Icons'

function mb(bytes: number) {
  return bytes > 1e9 ? `${(bytes / 1e9).toFixed(1)} GB` : `${(bytes / 1e6).toFixed(0)} MB`
}

function mmss(s: number) {
  return `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`
}

/** UTC ISO -> value for a datetime-local input in India time. */
function utcToIstInput(utc: string): string {
  return new Date(new Date(utc + (utc.endsWith('Z') ? '' : 'Z')).getTime() + 5.5 * 3600_000).toISOString().slice(0, 19)
}

function formatIst(utc: string) {
  return new Date(utc).toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', dateStyle: 'medium', timeStyle: 'short' })
}

function JobCard({ job, onRemove }: { job: VideoJob; onRemove: (id: number) => void }) {
  const pct = job.frames_total ? Math.round((job.frames_done / job.frames_total) * 100) : 0
  const tone = job.status === 'done' ? 'ok' : job.status === 'failed' ? 'bad' : 'beacon'
  return (
    <li className="rounded-xl border border-ink-700 bg-ink-900/60 p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="truncate text-sm font-medium text-ink-100">{job.original_name}</span>
        <Badge tone={tone}>{job.status}</Badge>
      </div>
      <p className="mt-0.5 text-xs text-ink-400">
        {job.sentinel_label} · recorded {job.recorded_at_utc ? formatIst(job.recorded_at_utc) : '—'}
        {job.recorded_at_source === 'video_metadata' ? ' (time from video file)' : ''}
        {job.route_length_m ? ` · route ${formatDistance(job.route_length_m)}` : ''}
      </p>
      {(job.status === 'processing' || job.status === 'queued') && (
        <div className="mt-2">
          <div className="h-2 overflow-hidden rounded-full bg-ink-700" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}>
            <div className="h-full bg-beacon-400 transition-all" style={{ width: `${pct}%` }} />
          </div>
          <p className="mt-1 text-xs text-ink-300">
            {job.stage ?? 'working'}
            {job.frames_total ? ` · ${job.frames_done} of ${job.frames_total} frames` : ''}
          </p>
        </div>
      )}
      {job.status === 'failed' && <p className="mt-2 text-sm text-danger">{job.error}</p>}
      {job.status === 'done' && (
        <div className="mt-2 space-y-1 text-xs text-ink-300">
          <p>
            {job.frames_done} frames on {job.streets_covered.length} streets ·{' '}
            {Object.entries(job.analysis).map(([k, v]) => `${v} ${k === 'pending' ? 'waiting for AI analysis' : k}`).join(', ')}
          </p>
          <p className="text-ink-400">{job.position_note}</p>
        </div>
      )}
      {(job.status === 'done' || job.status === 'failed') && (
        <button onClick={() => onRemove(job.id)} className="mt-2 text-xs text-ink-400 underline hover:text-ink-100">
          Remove this video's photos and observations
        </button>
      )}
    </li>
  )
}

export function VideoSentinel() {
  const map = useApi(() => api.map())
  const areaName = map.data?.source.area?.name ?? null
  const assets = useApi(api.assetVideos)
  const [jobs, setJobs] = useState<VideoJob[]>([])
  const [jobsLoaded, setJobsLoaded] = useState(false)
  const [jobsError, setJobsError] = useState<string | null>(null)
  const city = currentCity() // fixed for this page load: switching city reloads the page, so the list is fetched again
  const [video, setVideo] = useState<CheckedVideo | null>(null)
  const [checking, setChecking] = useState(false)
  const [uploadPct, setUploadPct] = useState<number | null>(null)
  const [videoError, setVideoError] = useState<string | null>(null)
  const [points, setPoints] = useState<[number, number][]>([])
  const [path, setPath] = useState<{ geometry: [number, number][]; length_m: number } | null>(null)
  const [traceError, setTraceError] = useState<string | null>(null)
  const [label, setLabel] = useState(SENTINEL_LABELS[0])
  const [useVideoTime, setUseVideoTime] = useState(false)
  const [recordedAt, setRecordedAt] = useState('')
  const [rideStart, setRideStart] = useState('')
  const [rideEnd, setRideEnd] = useState('')
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // The selected city's jobs, refreshed every 1.5 s so queued / processing jobs show progress.
  useEffect(() => {
    let stop = false
    const load = async () => {
      try {
        const r = await api.videoJobs(city)
        if (stop) return
        setJobs(r.jobs)
        setJobsLoaded(true)
        setJobsError(null)
      } catch (e) {
        if (!stop) setJobsError((e as Error).message) // the last list stays visible; the next round retries
      }
    }
    load()
    const id = setInterval(load, 1500)
    return () => {
      stop = true
      clearInterval(id)
    }
  }, [city])

  // Preview the traced path whenever points change.
  useEffect(() => {
    setTraceError(null)
    if (points.length < 2) return setPath(null)
    let cancelled = false
    api
      .traceRoute(points)
      .then((r) => !cancelled && setPath(r))
      .catch((e: ApiError) => {
        if (!cancelled) {
          setPath(null)
          setTraceError(e.message)
        }
      })
    return () => {
      cancelled = true
    }
  }, [points])

  const chooseVideo = (v: CheckedVideo) => {
    setVideo(v)
    setVideoError(null)
    if (v.info.creation_time_utc) setRecordedAt(utcToIstInput(v.info.creation_time_utc))
  }

  const pickAsset = async (name: string) => {
    setChecking(true)
    setVideo(null)
    setVideoError(null)
    try {
      chooseVideo(await api.checkAssetVideo(name))
    } catch (e) {
      setVideoError((e as Error).message)
    } finally {
      setChecking(false)
    }
  }

  const upload = async (file: File) => {
    setVideo(null)
    setVideoError(null)
    setUploadPct(0)
    try {
      chooseVideo(await api.uploadVideo(file, setUploadPct))
      assets.reload()
    } catch (e) {
      setVideoError((e as Error).message)
    } finally {
      setUploadPct(null)
    }
  }

  const submit = async () => {
    if (!video) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await api.createVideoJob({
        video_ref: video.video_ref,
        sentinel_label: label,
        waypoints: points,
        use_video_time: useVideoTime,
        recorded_at_ist: useVideoTime ? undefined : recordedAt,
        ride_start_s: rideStart ? Number(rideStart) : null,
        ride_end_s: rideEnd ? Number(rideEnd) : null,
        frame_interval_s: 5,
      })
      setVideo(null)
      setPoints([])
      setRideStart('')
      setRideEnd('')
      setJobs((await api.videoJobs(city)).jobs)
    } catch (e) {
      setSubmitError((e as Error).message)
    } finally {
      setSubmitting(false)
    }
  }

  const remove = async (id: number) => {
    if (!window.confirm('Remove all photos and observations from this video? The video file itself is kept.')) return
    try {
      await api.deleteVideoJob(id, city)
    } catch (e) {
      setSubmitError((e as Error).message)
    }
    try {
      setJobs((await api.videoJobs(city)).jobs) // refresh either way: a job that is already gone disappears
    } catch {
      /* the regular refresh shows the error */
    }
  }

  const ready = video && path && (useVideoTime || recordedAt)
  const frameCount = video ? Math.floor(((rideEnd ? Number(rideEnd) : video.info.duration_s) - (rideStart ? Number(rideStart) : 0)) / 5) : 0

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_380px]">
      <div className="space-y-5 rounded-2xl border border-ink-700 bg-ink-850 p-5">
        {/* 1. Video */}
        <section>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-300">1 · Choose the night-ride video</h2>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="rounded-xl border border-ink-700 p-3">
              <p className="text-xs text-ink-400">From assets/videos</p>
              {assets.loading ? (
                <LoadingBlock rows={2} />
              ) : assets.error ? (
                <ErrorState message={assets.error} onRetry={assets.reload} />
              ) : assets.data && assets.data.videos.length === 0 ? (
                <p className="mt-1 text-sm text-ink-300">
                  No videos there yet. Copy your night-ride videos into <code className="text-ink-100">assets/videos</code>, then{' '}
                  <button className="text-beacon-300 underline" onClick={assets.reload}>refresh</button>.
                </p>
              ) : (
                <ul className="mt-1 space-y-1">
                  {assets.data?.videos.map((v) => (
                    <li key={v.name}>
                      <button
                        disabled={!v.supported || checking}
                        onClick={() => pickAsset(v.name)}
                        className="flex w-full justify-between gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-ink-800 disabled:opacity-40"
                      >
                        <span className="truncate">{v.name}</span>
                        <span className="shrink-0 text-xs text-ink-400">{v.supported ? mb(v.size_bytes) : 'unsupported type'}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <label className="flex cursor-pointer flex-col justify-center rounded-xl border border-dashed border-ink-600 p-3 text-center hover:bg-ink-800">
              <span className="text-sm text-ink-100">Upload a video</span>
              <span className="text-xs text-ink-400">MP4, MOV, MKV, WEBM, AVI or 3GP · up to {VIDEO_UPLOAD_LIMIT_MB} MB</span>
              <input type="file" accept="video/*,.mkv,.3gp" className="sr-only" onChange={(e) => e.target.files?.[0] && upload(e.target.files[0])} />
            </label>
          </div>
          {uploadPct != null && (
            <div className="mt-3">
              <div className="h-2 overflow-hidden rounded-full bg-ink-700"><div className="h-full bg-beacon-400" style={{ width: `${uploadPct * 100}%` }} /></div>
              <p className="mt-1 text-xs text-ink-300">Uploading… {Math.round(uploadPct * 100)}% (then checking the file)</p>
            </div>
          )}
          {checking && <Skeleton className="mt-3 h-16 w-full" />}
          {videoError && <div className="mt-3"><ErrorState title="This video can't be used" message={videoError} /></div>}
          {video && (
            <div className="mt-3 rounded-xl border border-beacon-400/40 bg-beacon-400/5 p-3 text-sm">
              <p className="font-medium text-ink-100">{video.name}</p>
              <p className="mt-0.5 text-xs text-ink-300">
                {mmss(video.info.duration_s)} · {video.info.width}×{video.info.height} · {video.info.codec} · {mb(video.info.size_bytes)}
              </p>
              <p className="mt-1 text-xs text-ink-300">
                {video.info.location_tag
                  ? 'The file holds one location tag (where recording started). That is not a GPS track, so frame positions will come from the route you trace.'
                  : 'No GPS data in this video. Frame positions will come from the route you trace.'}
              </p>
            </div>
          )}
        </section>

        {/* 2. Route */}
        <section>
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-300">2 · Trace the ride</h2>
            <div className="flex gap-2 text-xs">
              <button className="rounded-lg bg-ink-800 px-2 py-1 disabled:opacity-40" disabled={!points.length} onClick={() => setPoints((p) => p.slice(0, -1))}>Undo</button>
              <button className="rounded-lg bg-ink-800 px-2 py-1 disabled:opacity-40" disabled={!points.length} onClick={() => setPoints([])}>Clear</button>
            </div>
          </div>
          <p className="mt-1 text-xs text-ink-400">Tap where the ride started, then each turn, then where it ended. The path follows the mapped streets.</p>
          <div className="mt-2 h-[340px] overflow-hidden rounded-xl border border-ink-700">
            {map.data ? <TraceMap data={map.data} points={points} path={path?.geometry ?? null} onAdd={(p) => setPoints((ps) => [...ps, p])} /> : <Skeleton className="h-full w-full rounded-none" />}
          </div>
          <p className="mt-1 text-xs text-ink-300" role="status">
            {traceError ?? (path ? `Route ${formatDistance(path.length_m)} along mapped streets.` : `${points.length} point${points.length === 1 ? '' : 's'} — add at least 2.`)}
          </p>
        </section>

        {/* 3. Details */}
        <section className="grid gap-3 sm:grid-cols-2">
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-300 sm:col-span-2">3 · Details</h2>
          <label className="text-sm">
            <span className="text-ink-400">Sentinel name</span>
            <select value={label} onChange={(e) => setLabel(e.target.value)} className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2">
              {SENTINEL_LABELS.map((l) => <option key={l}>{l}</option>)}
            </select>
          </label>
          <label className="text-sm">
            <span className="text-ink-400">Recording started (India time)</span>
            <input type="datetime-local" step={1} value={recordedAt} disabled={useVideoTime} onChange={(e) => setRecordedAt(e.target.value)}
              className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2 [color-scheme:light] disabled:opacity-50" />
          </label>
          {video?.info.creation_time_utc && (
            <label className="flex items-start gap-2 text-xs text-ink-300 sm:col-span-2">
              <input type="checkbox" checked={useVideoTime} onChange={(e) => setUseVideoTime(e.target.checked)} className="mt-0.5" />
              Use the time stored in the video ({formatIst(video.info.creation_time_utc + 'Z')}). Phones sometimes store when recording ended or when the file was copied — check it matches the ride.
            </label>
          )}
          <label className="text-sm">
            <span className="text-ink-400">Ride starts at (seconds into video, optional)</span>
            <input type="number" min={0} value={rideStart} onChange={(e) => setRideStart(e.target.value)} className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2" />
          </label>
          <label className="text-sm">
            <span className="text-ink-400">Ride ends at (seconds, optional)</span>
            <input type="number" min={0} value={rideEnd} onChange={(e) => setRideEnd(e.target.value)} className="mt-1 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2" />
          </label>
          <p className="text-xs text-ink-400 sm:col-span-2">
            One frame every 5 seconds{video ? ` → about ${Math.max(frameCount, 0)} frames` : ''}. Positions assume steady speed between the start and end of the ride; trim waiting time at either end for better placement.
          </p>
          {submitError && <div className="sm:col-span-2"><ErrorState title="Could not start processing" message={submitError} /></div>}
          <button
            disabled={!ready || submitting}
            onClick={submit}
            className="rounded-xl bg-beacon-400 px-4 py-3 font-semibold text-ink-950 disabled:opacity-40 sm:col-span-2"
          >
            {submitting ? 'Adding to queue…' : 'Process video'}
          </button>
        </section>
      </div>

      <aside className="space-y-3 rounded-2xl border border-ink-700 bg-ink-850 p-5">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-ink-300">Processing queue</h2>
          {areaName && <p className="text-xs text-ink-400">Videos of {areaName} only — switch the demo area to see another city's.</p>}
        </div>
        {jobsError && <ErrorState title={jobsLoaded ? 'Could not refresh the list' : 'Could not load the video list'} message={jobsError} />}
        {!jobsLoaded ? (
          !jobsError && <Skeleton className="h-24 w-full" />
        ) : jobs.length === 0 ? (
          <EmptyState icon={<CameraIcon size={22} />} title={areaName ? `No videos processed for ${areaName} yet` : 'No videos processed yet'}>
            Processing runs in the background, one video at a time. You can keep using ShadowMap meanwhile.
          </EmptyState>
        ) : (
          <ul className="space-y-2">{jobs.map((j) => <JobCard key={j.id} job={j} onRemove={remove} />)}</ul>
        )}
      </aside>
    </div>
  )
}
