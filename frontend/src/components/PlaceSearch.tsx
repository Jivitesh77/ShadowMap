// Top-bar search over ShadowMap's own data for the selected city: named places and named streets.
// Nothing is looked up on the internet; results are exactly what the map shows.
import { useEffect, useMemo, useRef, useState } from 'react'
import type { Place, Street } from '../api'
import { categoryMeta, placeName } from '../lib/mapMeta'
import { SearchIcon } from './Icons'

type Result =
  | { kind: 'place'; id: number; title: string; sub: string; lat: number; lon: number }
  | { kind: 'street'; id: number; title: string; sub: string; lat: number; lon: number }

export function PlaceSearch({ places, streets, areaName, onShow, onGo }: {
  places: Place[]
  streets: Street[]
  areaName: string
  onShow: (r: { kind: 'place' | 'street'; id: number }) => void
  onGo: (p: { lat: number; lon: number; label: string }) => void
}) {
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [cursor, setCursor] = useState(0)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false)
    document.addEventListener('mousedown', onDown)
    return () => document.removeEventListener('mousedown', onDown)
  }, [open])

  const results = useMemo<Result[]>(() => {
    const s = q.trim().toLowerCase()
    if (s.length < 2) return []
    const out: Result[] = []
    for (const p of places) {
      if (p.name && p.name.toLowerCase().includes(s)) {
        out.push({ kind: 'place', id: p.id, title: placeName(p), sub: categoryMeta(p.category).label, lat: p.lat, lon: p.lon })
      }
    }
    const seen = new Set<string>()
    for (const st of streets) {
      if (st.name && st.name.toLowerCase().includes(s) && !seen.has(st.name)) {
        seen.add(st.name)
        const mid = st.geometry[Math.floor(st.geometry.length / 2)]
        out.push({ kind: 'street', id: st.id, title: st.name, sub: 'Street', lat: mid[0], lon: mid[1] })
      }
    }
    const starts = (r: Result) => (r.title.toLowerCase().startsWith(s) ? 0 : 1)
    return out.sort((a, b) => starts(a) - starts(b) || a.title.localeCompare(b.title)).slice(0, 12)
  }, [q, places, streets])

  const choose = (r: Result) => {
    onShow({ kind: r.kind, id: r.id })
    setOpen(false)
  }

  return (
    <div ref={ref} className="relative w-full">
      <SearchIcon size={18} className="pointer-events-none absolute top-1/2 left-3.5 -translate-y-1/2 text-ink-400" />
      <input
        value={q}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setCursor(0) }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setCursor((c) => Math.min(c + 1, results.length - 1)) }
          if (e.key === 'ArrowUp') { e.preventDefault(); setCursor((c) => Math.max(c - 1, 0)) }
          if (e.key === 'Enter' && results[cursor]) choose(results[cursor])
          if (e.key === 'Escape') setOpen(false)
        }}
        placeholder={`Search places and streets in ${areaName}…`}
        aria-label="Search places and streets"
        role="combobox"
        aria-expanded={open && results.length > 0}
        className="h-11 w-full rounded-xl border border-ink-700 bg-ink-850 pr-3 pl-10 text-sm text-ink-100 placeholder:text-ink-400 focus:border-beacon-400"
      />
      {open && q.trim().length >= 2 && (
        <div className="sm-card absolute top-full right-0 left-0 z-[1400] mt-2 p-1.5">
          {results.length === 0 ? (
            <p className="px-3 py-2 text-sm text-ink-400">Nothing named “{q.trim()}” in this demo area’s map data.</p>
          ) : (
            <ul role="listbox" aria-label="Search results">
              {results.map((r, i) => (
                <li key={`${r.kind}-${r.id}`} className={`flex items-center gap-2 rounded-lg ${i === cursor ? 'bg-ink-900' : ''}`}>
                  <button role="option" aria-selected={i === cursor} onClick={() => choose(r)} onMouseEnter={() => setCursor(i)}
                    className="min-w-0 flex-1 px-3 py-2 text-left">
                    <span className="block truncate text-sm font-medium text-ink-100">{r.title}</span>
                    <span className="block text-xs text-ink-400">{r.sub}</span>
                  </button>
                  <button onClick={() => { onGo({ lat: r.lat, lon: r.lon, label: r.title }); setOpen(false) }}
                    className="mr-1.5 shrink-0 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-beacon-300 hover:bg-lavender-100">
                    Go here
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
