// Walk With Me (blueprint §9): start a walk, share a live link, "Are you safe?" with PIN, SOS, help bar, Where am I.
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type LatLon, type WalkConfig, type WalkerState, type WhereAmI } from '../api'
import { savedProfile, walkSession, type WalkSession } from '../lib/walkSession'
import { formatDistance, categoryMeta } from '../lib/mapMeta'
import { HelpBar } from './HelpBar'
import { ErrorState } from './States'

const TRIGGER_TEXT: Record<string, string> = {
  stopped: 'You have stopped for a while.',
  off_route: 'You are off your planned route.',
  late: 'You are later than expected.',
}

// ---------------- setup ----------------

export function WalkSetup({
  start,
  end,
  config,
  onStarted,
  onCancel,
}: {
  start: LatLon
  end: LatLon
  config: WalkConfig
  onStarted: (s: WalkSession) => void
  onCancel: () => void
}) {
  const saved = savedProfile.get()
  const [name, setName] = useState(saved?.walker_name ?? '')
  const [phone, setPhone] = useState(saved?.walker_phone ?? '')
  const [contacts, setContacts] = useState(saved?.contacts?.length ? saved.contacts : [{ name: '', phone: '' }])
  const [pin, setPin] = useState('')
  const [duress, setDuress] = useState('')
  const [simulate, setSimulate] = useState(config.demo_mode)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const valid = name.trim() && contacts.some((c) => c.name.trim()) && /^\d{4}$/.test(pin) && (!duress || (/^\d{4}$/.test(duress) && duress !== pin))

  const go = async (e: React.FormEvent) => {
    e.preventDefault()
    setBusy(true)
    setError(null)
    const cs = contacts.filter((c) => c.name.trim()).map((c) => ({ name: c.name.trim(), phone: c.phone.trim() || undefined }))
    try {
      const r = await api.startWalk({ walker_name: name.trim(), walker_phone: phone.trim() || undefined, contacts: cs, pin,
        duress_pin: duress || undefined, start, end, simulated: simulate })
      savedProfile.set({ walker_name: name.trim(), walker_phone: phone.trim(), contacts: contacts.filter((c) => c.name.trim()) })
      const s = { walk_id: r.walk_id, token: r.walker_token, walker_name: name.trim(), contact_path: r.contact_path, simulated: simulate }
      walkSession.set(s)
      onStarted(s)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const input = 'min-h-11 w-full rounded-lg border border-ink-600 bg-ink-900 px-3 text-sm'
  return (
    <form onSubmit={go} className="space-y-4">
      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-beacon-400">Walk With Me</p>
        <h2 className="mt-0.5 text-lg font-semibold">Let someone watch over this walk</h2>
        <p className="mt-1 text-xs text-ink-400">Your location is shared only during this walk, only with the people you add, and stops when you arrive.</p>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input className={input} placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} aria-label="Your name" />
        <input className={input} placeholder="Your phone (optional)" inputMode="tel" value={phone} onChange={(e) => setPhone(e.target.value)} aria-label="Your phone" />
      </div>
      <div className="space-y-2">
        <p className="text-xs text-ink-400">Trusted contacts (up to 3)</p>
        {contacts.map((c, i) => (
          <div key={i} className="grid grid-cols-2 gap-2">
            <input className={input} placeholder={`Contact ${i + 1} name`} value={c.name} aria-label={`Contact ${i + 1} name`}
              onChange={(e) => setContacts((cs) => cs.map((x, j) => (j === i ? { ...x, name: e.target.value } : x)))} />
            <input className={input} placeholder="Phone (optional)" inputMode="tel" value={c.phone} aria-label={`Contact ${i + 1} phone`}
              onChange={(e) => setContacts((cs) => cs.map((x, j) => (j === i ? { ...x, phone: e.target.value } : x)))} />
          </div>
        ))}
        {contacts.length < 3 && (
          <button type="button" onClick={() => setContacts((cs) => [...cs, { name: '', phone: '' }])} className="text-xs text-beacon-300 underline">
            Add another contact
          </button>
        )}
      </div>
      <div className="grid grid-cols-2 gap-2">
        <label className="text-xs text-ink-400">
          Your 4-digit PIN
          <input className={`${input} mt-1 tracking-[0.5em]`} type="password" inputMode="numeric" maxLength={4} value={pin}
            onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))} />
        </label>
        <label className="text-xs text-ink-400">
          Duress PIN (different)
          <input className={`${input} mt-1 tracking-[0.5em]`} type="password" inputMode="numeric" maxLength={4} value={duress}
            onChange={(e) => setDuress(e.target.value.replace(/\D/g, ''))} />
        </label>
      </div>
      <p className="text-xs text-ink-400">
        “I'm safe” needs your PIN, so nobody can cancel an alert by grabbing your phone. The duress PIN looks like it cancels, but silently alerts your contacts and the police dashboard.
      </p>
      {config.demo_mode && (
        <label className="flex items-start gap-2 rounded-lg border border-beacon-400/40 bg-beacon-400/10 p-2.5 text-xs text-ink-200">
          <input type="checkbox" checked={simulate} onChange={(e) => setSimulate(e.target.checked)} className="mt-0.5" />
          Demo: simulate walking along the route (for indoor demos). Contacts and the police dashboard see “simulated positions”.
        </label>
      )}
      {error && <ErrorState title="Walk not started" message={error} />}
      <div className="grid grid-cols-3 gap-2">
        <button type="button" onClick={onCancel} className="min-h-12 rounded-xl border border-ink-600 text-sm">Cancel</button>
        <button disabled={!valid || busy} className="col-span-2 min-h-12 rounded-xl bg-beacon-400 font-semibold text-ink-950 disabled:opacity-40">
          {busy ? 'Starting…' : 'Start walk'}
        </button>
      </div>
    </form>
  )
}

// ---------------- active walk ----------------

function haversine(a: [number, number], b: [number, number]) {
  const R = 6371000, toRad = (d: number) => (d * Math.PI) / 180
  const dLat = toRad(b[0] - a[0]), dLon = toRad(b[1] - a[1])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[0])) * Math.cos(toRad(b[0])) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

function pointAlong(route: [number, number][], m: number): [number, number] {
  for (let i = 0; i < route.length - 1; i++) {
    const seg = haversine(route[i], route[i + 1])
    if (m <= seg) {
      const t = seg ? m / seg : 0
      return [route[i][0] + t * (route[i + 1][0] - route[i][0]), route[i][1] + t * (route[i + 1][1] - route[i][1])]
    }
    m -= seg
  }
  return route[route.length - 1]
}

const SIM_SPEED_MS = 6 // demo: about 4x walking speed so the walk fits in a presentation

function PinPad({ title, sub, onSubmit, error, busy, children }: {
  title: string; sub?: string; onSubmit: (pin: string) => void; error: string | null; busy: boolean; children?: React.ReactNode
}) {
  const [pin, setPin] = useState('')
  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(pin); setPin('') }} className="space-y-3">
      <p className="text-2xl font-bold">{title}</p>
      {sub && <p className="text-sm text-ink-200">{sub}</p>}
      {children}
      <input autoFocus type="password" inputMode="numeric" maxLength={4} value={pin} aria-label="PIN"
        onChange={(e) => setPin(e.target.value.replace(/\D/g, ''))}
        className="min-h-14 w-full rounded-xl border border-ink-500 bg-ink-950 text-center text-2xl tracking-[0.6em]" />
      {error && <p className="text-sm font-semibold text-white" role="alert">{error}</p>}
      <button disabled={pin.length !== 4 || busy} className="min-h-14 w-full rounded-xl bg-white text-lg font-bold text-ink-950 disabled:opacity-50">
        {busy ? 'Checking…' : "I'm safe"}
      </button>
    </form>
  )
}

export function WalkActive({
  session,
  config,
  at,
  onPosition,
  onFinished,
}: {
  session: WalkSession
  config: WalkConfig
  at?: string
  onPosition: (p: LatLon) => void
  onFinished: () => void
}) {
  const [state, setState] = useState<WalkerState | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [where, setWhere] = useState<WhereAmI | null>(null)
  const [pinError, setPinError] = useState<string | null>(null)
  const [pinBusy, setPinBusy] = useState(false)
  const [ending, setEnding] = useState(false)
  const [paused, setPaused] = useState(false)
  const [offRoute, setOffRoute] = useState(false)
  const [sosHolding, setSosHolding] = useState(false)
  const [sosSent, setSosSent] = useState(false)
  const [copied, setCopied] = useState(false)
  const sosTimer = useRef<number | null>(null)
  const simM = useRef(0)
  const pos = useRef<LatLon | null>(null)
  const battery = useRef<number | undefined>(undefined)
  const link = `${window.location.origin}${session.contact_path}`

  const refresh = useCallback(async () => {
    try {
      const s = await api.walkState(session.walk_id, session.token)
      setState(s)
      setError(null)
      if (s.asking) navigator.vibrate?.([300, 200, 300])
    } catch (e) {
      const err = e as ApiError
      setError(err.message)
      if (err.status === 404 || err.status === 403) {
        walkSession.set(null)
        onFinished()
      }
    }
  }, [session, onFinished])

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 3000)
    return () => clearInterval(id)
  }, [refresh])

  // battery level, where the browser offers it (Android Chrome); contacts are told below 10 %
  useEffect(() => {
    const nav = navigator as unknown as { getBattery?: () => Promise<{ level: number }> }
    nav.getBattery?.().then((b) => (battery.current = Math.round(b.level * 100))).catch(() => {})
  }, [])

  // positions: simulated along the route (demo) or from the phone's GPS
  useEffect(() => {
    if (!state || ['arrived', 'ended'].includes(state.status)) return
    const send = (p: LatLon) => {
      pos.current = p
      onPosition(p)
      api.walkPosition(session.walk_id, session.token, { ...p, battery_pct: battery.current }).then(setState).catch(() => {})
    }
    if (session.simulated) {
      const id = setInterval(() => {
        if (!paused) simM.current += SIM_SPEED_MS * 3
        const [lat, lon] = pointAlong(state.route, simM.current)
        send({ lat: offRoute ? lat + 0.0008 : lat, lon })
      }, 3000)
      return () => clearInterval(id)
    }
    if (!('geolocation' in navigator) || !window.isSecureContext) {
      setError('Live location needs a secure (https) page and location permission. Positions are not being sent.')
      return
    }
    let latest: LatLon | null = null
    const watch = navigator.geolocation.watchPosition(
      (p) => (latest = { lat: p.coords.latitude, lon: p.coords.longitude }),
      (err) => setError(err.code === err.PERMISSION_DENIED ? 'Location permission was refused: your contacts cannot see where you are.' : 'Your position is not available right now.'),
      { enableHighAccuracy: true, maximumAge: 3000 },
    )
    const id = setInterval(() => latest && send(latest), 4000)
    return () => {
      navigator.geolocation.clearWatch(watch)
      clearInterval(id)
    }
  }, [session, state?.status, state?.route, paused, offRoute, onPosition]) // eslint-disable-line react-hooks/exhaustive-deps

  // Where am I card, refreshed every 20 s
  useEffect(() => {
    const load = () => pos.current && api.whereAmI(pos.current, at).then(setWhere).catch(() => {})
    const first = setTimeout(load, 1500)
    const id = setInterval(load, 20000)
    return () => {
      clearTimeout(first)
      clearInterval(id)
    }
  }, [at])

  const answer = async (pin: string) => {
    setPinBusy(true)
    setPinError(null)
    try {
      setState(await api.walkSafe(session.walk_id, session.token, pin))
      setEnding(false)
    } catch (e) {
      setPinError((e as Error).message)
    } finally {
      setPinBusy(false)
    }
  }

  const end = async (pin: string) => {
    setPinBusy(true)
    setPinError(null)
    try {
      await api.walkEnd(session.walk_id, session.token, pin)
      walkSession.set(null)
      onFinished()
    } catch (e) {
      setPinError((e as Error).message)
    } finally {
      setPinBusy(false)
    }
  }

  const startSos = () => {
    setSosHolding(true)
    sosTimer.current = window.setTimeout(async () => {
      setSosHolding(false)
      try {
        await api.walkSos(session.walk_id, session.token)
        setSosSent(true)
        navigator.vibrate?.(500)
      } catch (e) {
        setError((e as Error).message)
      }
    }, 2000)
  }
  const stopSos = () => {
    setSosHolding(false)
    if (sosTimer.current) clearTimeout(sosTimer.current)
  }

  const share = async () => {
    const text = `Follow my walk live on ShadowMap: ${link}`
    try {
      if (navigator.share) await navigator.share({ title: 'ShadowMap walk', text, url: link })
      else {
        await navigator.clipboard.writeText(link)
        setCopied(true)
      }
    } catch {
      /* user closed the share sheet */
    }
  }

  if (!state) return <p className="text-sm text-ink-400">{error ?? 'Starting your walk…'}</p>

  const done = state.status === 'arrived' || state.status === 'ended'
  const eta = state.expected_arrival_utc ? new Date(state.expected_arrival_utc).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' }) : '—'
  const asked = state.check_started_utc ? Math.floor((Date.now() - new Date(state.check_started_utc).getTime()) / 1000) : 0
  const left = Math.max(0, state.timers.ask_s - asked)

  return (
    <div className="space-y-4 pb-2">
      {state.asking && (
        <div className="fixed inset-0 z-[2500] flex items-center justify-center bg-danger/95 p-6" role="alertdialog" aria-label="Are you safe?">
          <div className="w-full max-w-sm">
            <PinPad title="Are you safe?" error={pinError} busy={pinBusy} onSubmit={answer}
              sub={`${TRIGGER_TEXT[state.trigger ?? ''] ?? ''} ${state.escalation >= 2 ? 'Your contacts have been alerted.' : `Answer within ${left} s or your contacts will be alerted.`}`}>
              {state.escalation >= 3 && <p className="rounded-lg bg-white/15 p-2 text-sm">The police dashboard has been alerted (simulated).</p>}
            </PinPad>
          </div>
        </div>
      )}
      {ending && !state.asking && (
        <div className="fixed inset-0 z-[2400] flex items-center justify-center bg-ink-950/95 p-6">
          <div className="w-full max-w-sm">
            <PinPad title="End walk" sub="Enter your PIN to stop sharing your location." error={pinError} busy={pinBusy} onSubmit={end} />
            <button onClick={() => setEnding(false)} className="mt-3 w-full text-sm text-ink-300 underline">Keep walking</button>
          </div>
        </div>
      )}

      <div>
        <p className="text-xs font-semibold uppercase tracking-wider text-beacon-400">Walk With Me</p>
        <h2 className="mt-0.5 text-lg font-semibold">
          {state.status === 'arrived' ? 'You have arrived' : state.status === 'ended' ? 'Walk ended' : `Walking · arriving about ${eta}`}
        </h2>
        {session.simulated && <p className="text-xs text-beacon-300">Demo: positions are simulated along the route.</p>}
      </div>

      {error && <ErrorState title="Walk" message={error} />}

      {done ? (
        <button onClick={() => { walkSession.set(null); onFinished() }} className="min-h-12 w-full rounded-xl bg-beacon-400 font-semibold text-ink-950">Done</button>
      ) : (
        <>
          <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-3 text-sm">
            <p className="text-xs text-ink-400">Your contacts follow this link (no app needed)</p>
            <p className="mt-1 truncate text-ink-100">{link}</p>
            <div className="mt-2 grid grid-cols-2 gap-2">
              <button onClick={share} className="min-h-10 rounded-lg border border-ink-600 text-sm">{copied ? 'Link copied' : 'Share link'}</button>
              <a href={`https://wa.me/?text=${encodeURIComponent(`Follow my walk live on ShadowMap: ${link}`)}`} target="_blank" rel="noreferrer"
                className="grid min-h-10 place-items-center rounded-lg border border-ink-600 text-sm">WhatsApp</a>
            </div>
            <p className="mt-2 text-xs text-ink-400">Watching: {state.contacts.map((c) => c.name).join(', ')}</p>
          </div>

          {where && (
            <div className="rounded-xl border border-ink-600 bg-ink-800 p-3" aria-label="Where am I">
              <p className="text-xs font-semibold uppercase tracking-wider text-ink-400">Where am I — read this to the operator</p>
              <p className="mt-1 text-base font-semibold text-ink-100">{where.street ? `On ${where.street}` : 'Not on a mapped street'}</p>
              {where.landmark && <p className="text-sm text-ink-200">Near {where.landmark.name} ({formatDistance(where.landmark.distance_m)})</p>}
              <p className="text-sm text-ink-200">
                {where.nearest_open ? `Nearest open place: ${where.nearest_open.name ?? categoryMeta(where.nearest_open.category).label}, ${formatDistance(where.nearest_open.distance_m)}` : 'No place known to be open nearby.'}
              </p>
              {where.nearest_police && <p className="text-sm text-ink-200">Police: {where.nearest_police.name}, {formatDistance(where.nearest_police.distance_m)}</p>}
            </div>
          )}

          <div className="grid grid-cols-2 gap-2">
            <button onPointerDown={startSos} onPointerUp={stopSos} onPointerLeave={stopSos} onContextMenu={(e) => e.preventDefault()}
              className={`min-h-14 rounded-xl text-base font-bold ${sosHolding ? 'bg-white text-danger' : 'bg-danger text-white'}`}>
              {sosSent ? 'SOS sent' : sosHolding ? 'Keep holding…' : 'SOS (hold 2 s)'}
            </button>
            <button onClick={() => { setPinError(null); setEnding(true) }} className="min-h-14 rounded-xl border border-ink-600 text-sm font-semibold">End walk</button>
          </div>

          {session.simulated && (
            <div className="grid grid-cols-2 gap-2 text-xs">
              <button onClick={() => setPaused((p) => !p)} className="min-h-10 rounded-lg border border-beacon-400/50 text-beacon-300">
                {paused ? 'Demo: start moving' : 'Demo: stand still'}
              </button>
              <button onClick={() => setOffRoute((o) => !o)} className="min-h-10 rounded-lg border border-beacon-400/50 text-beacon-300">
                {offRoute ? 'Demo: back on route' : 'Demo: walk off route'}
              </button>
            </div>
          )}

          <div className="sticky bottom-20 z-20 rounded-2xl border border-ink-700 bg-ink-950/95 p-2 backdrop-blur lg:bottom-2">
            <HelpBar config={config} policeStation={where?.nearest_police ?? null} contactPhone={state.contacts.find((c) => c.phone)?.phone ?? null}
              onCalling={(t) => api.walkNote(session.walk_id, session.token, t).catch(() => {})} />
          </div>
        </>
      )}
    </div>
  )
}
