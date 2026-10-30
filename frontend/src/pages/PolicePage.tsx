// Police / control-room dashboard (blueprint §11). SIMULATED: not connected to any real police system.
import { useEffect, useState } from 'react'
import { api, type PoliceAlert } from '../api'
import { useApi } from '../hooks/useApi'
import { LiveMap } from '../components/LiveMap'
import { ShieldIcon } from '../components/Icons'
import { EmptyState, ErrorState, LoadingBlock } from '../components/States'
import { Badge, PageHeader, Panel, Stat } from '../components/Ui'

const KEY = 'sm-police-code'
const getCode = () => { try { return localStorage.getItem(KEY) } catch { return null } }
const setCode = (c: string | null) => { try { if (c) localStorage.setItem(KEY, c); else localStorage.removeItem(KEY) } catch { /* memory only */ } }
const TRIGGER: Record<string, string> = { stopped: 'Stopped, no answer', off_route: 'Off route, no answer', late: 'Late, no answer', sos: 'SOS pressed', duress: 'DURESS PIN', no_answer: 'No answer', sos_after_end: 'SOS after the walk ended', duress_after_end: 'DURESS PIN after the walk ended' }
const STATUS: Record<PoliceAlert['status'], string> = { new: 'New', acknowledged: 'Acknowledged', unit_sent: 'Unit sent', resolved: 'Resolved' }
const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit', second: '2-digit' }) : '—')

function Gate({ onOk }: { onOk: (c: string) => void }) {
  const [code, setC] = useState('')
  const [err, setErr] = useState<string | null>(null)
  return (
    <form className="mx-auto max-w-md space-y-3 rounded-2xl border border-ink-700 bg-ink-850 p-5" onSubmit={async (e) => {
      e.preventDefault()
      try { await api.policeAlerts(code.trim(), 'active'); setCode(code.trim()); onOk(code.trim()) } catch (x) { setErr((x as Error).message) }
    }}>
      <h2 className="text-lg font-semibold">Control room access code</h2>
      <p className="text-sm text-ink-300">Live positions of people in an alert are shown here. The code is set in <code>backend/.env</code> (POLICE_TOKEN).</p>
      <input type="password" value={code} onChange={(e) => setC(e.target.value)} aria-label="Access code" className="w-full rounded-lg border border-ink-600 bg-ink-900 px-3 py-2" />
      {err && <ErrorState title="Not accepted" message={err} />}
      <button disabled={!code.trim()} className="w-full rounded-xl bg-beacon-400 px-4 py-2.5 font-semibold text-ink-950 disabled:opacity-40">Open dashboard</button>
    </form>
  )
}

function AlertDetail({ a, code, onChanged }: { a: PoliceAlert; code: string; onChanged: () => void }) {
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const next = (['acknowledged', 'unit_sent', 'resolved'] as const).filter((s) => ['new', 'acknowledged', 'unit_sent', 'resolved'].indexOf(s) > ['new', 'acknowledged', 'unit_sent', 'resolved'].indexOf(a.status))
  const set = async (s: (typeof next)[number]) => {
    setBusy(true); setErr(null)
    try { await api.policeStatus(code, a.id, s); onChanged() } catch (e) { setErr((e as Error).message) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-3">
      <div className="h-[46vh] min-h-[300px] overflow-hidden rounded-xl border border-ink-700">
        <LiveMap route={a.route} live={a.live_position} lastMoved={a.last_moved} dest={a.dest} alertAt={a.alert_position} />
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-ink-300">
        <span><span className="mr-1 inline-block h-3 w-3 rounded-full bg-[#60a5fa] align-middle" />Live position {a.live_position_utc ? time(a.live_position_utc) : '(not shared)'}</span>
        <span><span className="mr-1 inline-block h-3 w-3 rounded-full bg-ink-300 align-middle" />Last seen moving {time(a.last_moved_utc)}</span>
        <span><span className="mr-1 inline-block h-3 w-3 rounded-full bg-danger align-middle" />Alert raised here</span>
        {a.simulated_positions && <Badge tone="warn">Positions simulated (demo)</Badge>}
      </div>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <div><dt className="text-ink-400">Person</dt><dd className="font-semibold">{a.walker_name}</dd></div>
        <div><dt className="text-ink-400">Phone</dt><dd>{a.walker_phone ?? 'not given'}</dd></div>
        <div><dt className="text-ink-400">Reason</dt><dd className={a.duress || a.trigger.startsWith('sos') ? 'font-bold text-danger' : ''}>{TRIGGER[a.trigger] ?? a.trigger}</dd></div>
        <div><dt className="text-ink-400">Raised</dt><dd>{time(a.created_utc)}</dd></div>
        <div><dt className="text-ink-400">Walk status</dt><dd>{a.walk_status}</dd></div>
        <div><dt className="text-ink-400">Contacts</dt><dd>{a.contacts.join(', ') || '—'}</dd></div>
      </dl>
      <p className="text-xs text-ink-400">Latest street photo: available once photos are blurred (next milestone).</p>
      {next.length > 0 && (
        <div className="grid grid-cols-3 gap-2">
          {next.map((s) => (
            <button key={s} disabled={busy} onClick={() => set(s)} className={`min-h-11 rounded-lg text-sm font-semibold ${s === 'resolved' ? 'border border-ink-600' : 'bg-beacon-400 text-ink-950'} disabled:opacity-50`}>
              {STATUS[s]}
            </button>
          ))}
        </div>
      )}
      {err && <ErrorState message={err} />}
      <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">History</h3>
      <ol className="space-y-1 text-sm">{a.history.map((h, i) => <li key={i}><span className="text-ink-400">{time(h.at)}</span> {STATUS[h.status as PoliceAlert['status']] ?? h.status} · {h.by}</li>)}</ol>
    </div>
  )
}

export default function PolicePage() {
  const [code, setCodeState] = useState<string | null>(getCode)
  const [scope, setScope] = useState<'active' | 'history'>('active')
  const [selected, setSelected] = useState<number | null>(null)
  const alerts = useApi(() => (code ? api.policeAlerts(code, scope) : Promise.resolve(null)), code ? 3000 : undefined, `${code}|${scope}`)
  const coverage = useApi(() => (code ? api.policeCoverage(code) : Promise.resolve(null)), code ? 30000 : undefined, code ?? '')
  const list = alerts.data?.alerts ?? []
  const current = list.find((a) => a.id === selected) ?? list[0]
  useEffect(() => { if (alerts.error?.includes('access code')) { setCode(null); setCodeState(null) } }, [alerts.error])

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader eyebrow="Operations" title="Police control room"
        description="Alerts from walkers who did not answer “Are you safe?”, pressed SOS or entered a duress PIN — with live position, route and where they last moved."
        aside={<Badge tone="warn">Simulated — not connected to any police system</Badge>} />
      {!code ? <Gate onOk={setCodeState} /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat label="Open alerts" value={scope === 'active' ? list.length : null} loading={alerts.loading && !alerts.data} />
            <Stat label="New (not acknowledged)" value={scope === 'active' ? list.filter((a) => a.status === 'new').length : null} loading={alerts.loading && !alerts.data} />
            <Stat label="Streets seen by Sentinels (1 h)" value={coverage.data?.streets_seen_last_hour} loading={coverage.loading} hint={coverage.data ? `of ${coverage.data.streets_in_area} in the area` : undefined} />
            <Stat label="Showing" value={null} loading={false} hint={scope === 'active' ? 'Active alerts' : 'Last 100 alerts'} />
          </div>
          <div role="tablist" className="inline-flex rounded-xl border border-ink-700 bg-ink-900 p-1">
            {(['active', 'history'] as const).map((s) => (
              <button key={s} role="tab" aria-selected={scope === s} onClick={() => { setScope(s); setSelected(null) }}
                className={`rounded-lg px-4 py-2 text-sm font-medium ${scope === s ? 'bg-beacon-400 text-ink-950' : 'text-ink-300'}`}>{s === 'active' ? 'Active' : 'History'}</button>
            ))}
          </div>
          {alerts.error && !alerts.data ? <ErrorState message={alerts.error} onRetry={alerts.reload} /> : alerts.loading && !alerts.data ? <LoadingBlock /> : list.length === 0 ? (
            <Panel><EmptyState icon={<ShieldIcon size={22} />} title={scope === 'active' ? 'No active alerts' : 'No alerts yet'}>Alerts appear here, newest first, when a walker does not respond to a safety check, presses SOS or enters a duress PIN. Positions are shown only while an alert is open.</EmptyState></Panel>
          ) : (
            <div className="grid gap-4 lg:grid-cols-[340px_minmax(0,1fr)]">
              <ul className="space-y-2">
                {list.map((a) => (
                  <li key={a.id}>
                    <button onClick={() => setSelected(a.id)} className={`w-full rounded-xl border p-3 text-left ${current?.id === a.id ? 'border-beacon-400 bg-beacon-400/10' : 'border-ink-700 bg-ink-850'} ${a.status === 'new' ? 'ring-2 ring-danger' : ''}`}>
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold">{a.walker_name}</span>
                        <Badge tone={a.status === 'resolved' ? 'neutral' : a.status === 'new' ? 'bad' : 'warn'}>{STATUS[a.status]}</Badge>
                      </div>
                      <p className={`text-sm ${a.duress || a.trigger.startsWith('sos') ? 'font-semibold text-danger' : 'text-ink-300'}`}>{TRIGGER[a.trigger] ?? a.trigger}</p>
                      <p className="text-xs text-ink-400">{time(a.created_utc)}</p>
                    </button>
                  </li>
                ))}
              </ul>
              <Panel>{current && <AlertDetail a={current} code={code} onChanged={alerts.reload} />}</Panel>
            </div>
          )}
          <button onClick={() => { setCode(null); setCodeState(null) }} className="text-xs text-ink-400 underline">Forget the access code on this device</button>
        </>
      )}
    </div>
  )
}
