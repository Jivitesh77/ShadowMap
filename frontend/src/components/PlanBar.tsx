// The route planning bar on the Walker page: starting point, destination, travel time and "Compare routes".
// Points come from the user's location, a tap on the map, or a named place from ShadowMap's own map data.
import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import type { LatLon } from '../api'
import { ChevronDownIcon, ClockIcon, CrosshairIcon, FlagIcon, MapPinIcon, SearchIcon } from './Icons'
import type { NamedPoint, PickTarget } from './RoutePanel'

export interface ChosenPoint {
  point: LatLon
  label: string
}

/** A field that opens a small panel below it; closes on outside click, Escape or after a choice. */
function Field({ icon, caption, value, placeholder, open, setOpen, children, active }: {
  icon: ReactNode
  caption: string
  value: string | null
  placeholder: string
  open: boolean
  setOpen: (v: boolean) => void
  children: ReactNode
  active?: boolean
}) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open, setOpen])
  return (
    <div ref={ref} className="relative min-w-0">
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className={`flex w-full items-center gap-3 rounded-xl px-2 py-2 text-left transition-colors hover:bg-ink-900 ${active ? 'bg-lavender-50 ring-1 ring-beacon-400' : ''}`}>
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-ink-900 text-ink-300">{icon}</span>
        <span className="min-w-0 flex-1">
          <span className="block text-[11px] font-semibold uppercase tracking-wider text-ink-400">{caption}</span>
          <span className={`flex items-center gap-1 text-sm font-medium ${value ? 'text-ink-100' : 'text-ink-300'}`}>
            <span className="truncate">{value ?? placeholder}</span>
            <ChevronDownIcon size={16} className="shrink-0 text-ink-400" />
          </span>
        </span>
      </button>
      {open && (
        <div className="sm-card absolute top-full left-0 z-[1050] mt-2 w-[min(92vw,360px)] p-2" role="dialog" aria-label={caption}>
          {children}
        </div>
      )}
    </div>
  )
}

function PointChooser({ places, onChoose, onMine, onMap, busy }: {
  places: NamedPoint[]
  onChoose: (p: ChosenPoint) => void
  onMine: () => void
  onMap: () => void
  busy: boolean
}) {
  const [q, setQ] = useState('')
  const matches = useMemo(() => {
    const s = q.trim().toLowerCase()
    return (s ? places.filter((p) => p.label.toLowerCase().includes(s)) : places).slice(0, 60)
  }, [q, places])
  return (
    <div className="space-y-1">
      <button onClick={onMine} disabled={busy} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-ink-900 disabled:opacity-50">
        <CrosshairIcon size={18} className="text-beacon-300" /> {busy ? 'Finding you…' : 'Use my location'}
      </button>
      <button onClick={onMap} className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-ink-900">
        <MapPinIcon size={18} className="text-beacon-300" /> Choose on the map
      </button>
      <div className="relative mt-1 border-t border-ink-700 pt-2">
        <SearchIcon size={16} className="absolute top-[18px] left-2.5 text-ink-400" />
        <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filter named places…" aria-label="Filter named places"
          className="w-full rounded-lg border border-ink-700 bg-ink-900 py-2 pr-2 pl-8 text-sm" />
      </div>
      <ul className="max-h-64 overflow-y-auto" role="listbox" aria-label="Named places">
        {matches.length === 0 && <li className="px-2 py-2 text-sm text-ink-400">No named place matches.</li>}
        {matches.map((p) => (
          <li key={p.label}>
            <button role="option" aria-selected={false} onClick={() => onChoose({ point: p.point, label: p.label.split(' · ')[0] })}
              className="w-full truncate rounded-lg px-2 py-1.5 text-left text-sm text-ink-100 hover:bg-ink-900">
              {p.label}
            </button>
          </li>
        ))}
      </ul>
      <p className="px-2 pt-1 text-[11px] text-ink-400">Named places from OpenStreetMap and team checks in this demo area.</p>
    </div>
  )
}

export function PlanBar({ start, end, onSet, places, picking, setPicking, onMine, locating, at, setAt, tonight, onCompare, canCompare, loading, onClear }: {
  start: ChosenPoint | null
  end: ChosenPoint | null
  onSet: (which: 'start' | 'end', p: ChosenPoint) => void
  places: NamedPoint[]
  picking: PickTarget
  setPicking: (p: PickTarget) => void
  onMine: (which: 'start' | 'end') => void
  locating: 'start' | 'end' | null
  at: string | undefined
  setAt: (at: string | undefined) => void
  tonight: string
  onCompare: () => void
  canCompare: boolean
  loading: boolean
  onClear: () => void
}) {
  const [open, setOpen] = useState<'start' | 'end' | 'time' | null>(null)
  const timeLabel = !at ? 'Now' : at === tonight ? 'Tonight 11:30 pm'
    : new Date(`${at}:00`).toLocaleString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })
  const field = (which: 'start' | 'end') => ({
    open: open === which,
    setOpen: (v: boolean) => setOpen(v ? which : null),
    active: picking === which,
  })
  const chooser = (which: 'start' | 'end') => (
    <PointChooser places={places} busy={locating === which}
      onChoose={(p) => { onSet(which, p); setOpen(null) }}
      onMine={() => { onMine(which); setOpen(null) }}
      onMap={() => { setPicking(which); setOpen(null) }} />
  )
  return (
    <section className="sm-card grid grid-cols-1 gap-1 p-2 sm:p-3 md:grid-cols-3 md:items-center lg:grid-cols-[1fr_1fr_1fr_auto] lg:gap-0 lg:divide-x lg:divide-ink-700" aria-label="Plan a route">
      <div className="lg:pr-3">
        <Field icon={<MapPinIcon size={18} />} caption="Starting point" value={picking === 'start' ? 'Tap the map…' : start?.label ?? null}
          placeholder="Choose a start" {...field('start')}>
          {chooser('start')}
        </Field>
      </div>
      <div className="lg:px-3">
        <Field icon={<FlagIcon size={18} />} caption="Destination" value={picking === 'end' ? 'Tap the map…' : end?.label ?? null}
          placeholder="Add a destination" {...field('end')}>
          {chooser('end')}
        </Field>
      </div>
      <div className="lg:px-3">
        <Field icon={<ClockIcon size={18} />} caption="Travel time (IST)" value={timeLabel} placeholder="Now"
          open={open === 'time'} setOpen={(v) => setOpen(v ? 'time' : null)}>
          <div className="space-y-1">
            <button onClick={() => { setAt(undefined); setOpen(null) }} className={`w-full rounded-lg px-2 py-2 text-left text-sm hover:bg-ink-900 ${!at ? 'font-semibold text-beacon-300' : ''}`}>Now</button>
            <button onClick={() => { setAt(tonight); setOpen(null) }} className={`w-full rounded-lg px-2 py-2 text-left text-sm hover:bg-ink-900 ${at === tonight ? 'font-semibold text-beacon-300' : ''}`}>Tonight 11:30 pm</button>
            <label className="block border-t border-ink-700 px-2 pt-2 text-xs text-ink-400">
              Another time
              <input type="datetime-local" aria-label="Choose walk time" value={at ?? ''} onChange={(e) => setAt(e.target.value || undefined)}
                className="mt-1 w-full rounded-lg border border-ink-700 bg-ink-900 px-2 py-1.5 text-sm text-ink-100 [color-scheme:light]" />
            </label>
            <p className="px-2 pt-1 text-[11px] text-ink-400">Open / closed places and scores are judged for this time.</p>
          </div>
        </Field>
      </div>
      <div className="flex items-center gap-2 pt-1 md:col-span-3 lg:col-span-1 lg:pl-3 lg:pt-0">
        {(start || end) && (
          <button onClick={onClear} className="min-h-12 rounded-xl px-3 text-sm text-ink-300 hover:bg-ink-900">Clear</button>
        )}
        <button onClick={onCompare} disabled={!canCompare || loading}
          className="min-h-12 flex-1 rounded-xl bg-beacon-400 px-5 text-sm font-semibold whitespace-nowrap text-white shadow-sm transition-colors hover:bg-beacon-500 disabled:bg-lavender-200 disabled:text-beacon-300 lg:flex-none">
          {loading ? 'Comparing…' : 'Compare routes →'}
        </button>
      </div>
    </section>
  )
}
