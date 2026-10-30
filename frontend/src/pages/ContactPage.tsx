// Trusted contact's live trip page (blueprint §9). Works from the shared link, no app or login needed.
import { api, type ContactView } from '../api'
import { useApi } from '../hooks/useApi'
import { LiveMap } from '../components/LiveMap'
import { UsersIcon } from '../components/Icons'
import { EmptyState, ErrorState, Skeleton } from '../components/States'
import { PageHeader, Panel } from '../components/Ui'

const time = (iso: string | null) => (iso ? new Date(iso).toLocaleTimeString('en-IN', { hour: 'numeric', minute: '2-digit' }) : '—')
const ago = (iso: string | null) => (iso ? `${Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 1000))} s ago` : '')

function Banner({ v }: { v: ContactView }) {
  if (v.duress)
    return <div className="rounded-2xl bg-danger p-4 text-white" role="alert"><p className="text-lg font-bold">EMERGENCY: {v.walker_name} entered her duress PIN.</p><p className="text-sm">She may be being forced to cancel. The police dashboard has been alerted (simulated). Call her and the police.</p></div>
  if (v.status === 'alert')
    return <div className="rounded-2xl bg-danger p-4 text-white" role="alert"><p className="text-lg font-bold">ALERT: {v.walker_name} has not answered “Are you safe?”</p><p className="text-sm">{v.escalation >= 3 ? 'The police dashboard has been alerted (simulated). ' : ''}Her live location is on the map. Try calling her now.</p></div>
  if (v.status === 'checking')
    return <div className="rounded-2xl bg-caution/20 p-4 ring-1 ring-caution" role="status"><p className="font-semibold">ShadowMap is asking {v.walker_name} “Are you safe?”</p><p className="text-sm text-ink-300">You will be alerted if she does not answer.</p></div>
  if (v.status === 'arrived')
    return <div className="rounded-2xl bg-safe/15 p-4 ring-1 ring-safe" role="status"><p className="text-lg font-semibold">{v.walker_name} reached safely at {time(v.ended_utc)}.</p><p className="text-sm text-ink-300">Location sharing has stopped.</p></div>
  if (v.status === 'ended')
    return <div className="rounded-2xl bg-ink-800 p-4" role="status"><p className="font-semibold">{v.walker_name} ended the walk at {time(v.ended_utc)}.</p><p className="text-sm text-ink-300">Location sharing has stopped.</p></div>
  return <div className="rounded-2xl bg-ink-800 p-4 ring-1 ring-ink-600" role="status"><p className="text-lg font-semibold">{v.walker_name} is walking</p><p className="text-sm text-ink-300">Expected to arrive about {time(v.expected_arrival_utc)}.</p></div>
}

export default function ContactPage({ tripId }: { tripId?: string }) {
  const trip = useApi(() => (tripId ? api.contactView(tripId) : Promise.resolve(null)), tripId ? 3000 : undefined, tripId ?? '')
  const v = trip.data

  if (!tripId)
    return (
      <div className="mx-auto max-w-4xl space-y-6">
        <PageHeader eyebrow="Trusted contact" title="Follow a walk" description="When someone adds you as a trusted contact, their trip link shows their live position, planned route and expected arrival, and alerts you if they stop responding." />
        <Panel>
          <EmptyState icon={<UsersIcon size={22} />} title="No trip open">Open the trip link the walker shared with you. It looks like <span className="text-ink-300">/trip/…</span> and works without installing anything.</EmptyState>
        </Panel>
      </div>
    )

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <PageHeader eyebrow="Trusted contact" title={v ? `${v.walker_name}'s walk` : 'Live trip'} description="Updates every few seconds. Location is shared only during the walk and stops on arrival." />
      {trip.error && !v ? (
        <ErrorState title="Trip not available" message={trip.error} onRetry={trip.reload} />
      ) : !v ? (
        <Skeleton className="h-64 w-full" />
      ) : (
        <>
          <Banner v={v} />
          <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="h-[55vh] min-h-[320px] overflow-hidden rounded-2xl border border-ink-700">
              {v.route || v.last ? <LiveMap route={v.route} live={v.last} dest={v.dest} /> : (
                <div className="grid h-full place-items-center bg-ink-850 p-6 text-center text-sm text-ink-400">The walk is over; the map is no longer shared.</div>
              )}
            </div>
            <aside className="space-y-3 rounded-2xl border border-ink-700 bg-ink-850 p-4">
              {v.last && <p className="text-xs text-ink-400">Last position {ago(v.last_position_utc)}{v.simulated ? ' · simulated for the demo' : ''}{v.battery_pct != null ? ` · battery ${v.battery_pct}%` : ''}</p>}
              {v.walker_phone && <a href={`tel:${v.walker_phone.replace(/\s/g, '')}`} className="grid min-h-12 place-items-center rounded-xl bg-beacon-400 font-semibold text-ink-950">Call {v.walker_name}</a>}
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-400">Timeline</h3>
              <ol className="space-y-2">
                {[...v.events].reverse().map((e, i) => (
                  <li key={i} className={`rounded-lg p-2 text-sm ${e.kind.startsWith('alert') || e.kind === 'sos' || e.kind === 'duress' ? 'bg-danger/15 text-ink-100' : 'bg-ink-900/60 text-ink-200'}`}>
                    <span className="block text-xs text-ink-400">{time(e.at)}</span>{e.text}
                  </li>
                ))}
              </ol>
            </aside>
          </div>
        </>
      )}
      {trip.error && v && <p className="text-xs text-ink-400">Connection problem, retrying… ({trip.error})</p>}
    </div>
  )
}

