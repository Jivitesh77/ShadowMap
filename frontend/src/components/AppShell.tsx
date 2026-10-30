// The frame around every page.
// Laptops: an icon-only sidebar that expands over the page on hover (or keyboard focus) and collapses on mouse leave.
// It floats above the content, so the page and the map underneath never move, resize or reload.
// Phones: a top bar with a menu button that opens a drawer. A top search slot is filled by pages that support search.
import { createContext, useEffect, useRef, useState, type ReactNode } from 'react'
import { api, type CitiesInfo, type Health } from '../api'
import { useApi, type ApiState } from '../hooks/useApi'
import { currentCity, switchCity } from '../lib/city'
import { savedProfile, walkSession } from '../lib/walkSession'
import { navigate, type RouteName } from '../router'
import { BellIcon, BuildingIcon, CameraIcon, LogoMark, MapPinIcon, MenuIcon, RouteIcon, ShieldIcon, UserIcon, UsersIcon, XIcon } from './Icons'

/** Pages render their search box into this element (see WalkerPage) with a React portal. */
export const TopBarSlotContext = createContext<HTMLElement | null>(null)

interface NavItem {
  name: RouteName
  label: string
  path: string
  icon: (p: { size?: number }) => ReactNode
}

const GROUPS: { title: string; items: NavItem[] }[] = [
  { title: 'Plan', items: [{ name: 'walker', label: 'Plan a safer walk', path: '/', icon: RouteIcon }] },
  { title: 'Your circle', items: [{ name: 'contact', label: 'Trusted contact', path: '/trip', icon: UsersIcon }] },
  {
    title: 'Apps',
    items: [
      { name: 'sentinel', label: 'Sentinel', path: '/sentinel', icon: CameraIcon },
      { name: 'police', label: 'Police control room', path: '/police', icon: ShieldIcon },
      { name: 'city', label: 'City dashboard', path: '/city', icon: BuildingIcon },
    ],
  },
]

const COLLAPSED = 'w-[76px]'
const EXPANDED = 'w-64'

function NavLink({ item, active, showLabel, onDone }: { item: NavItem; active: boolean; showLabel: boolean; onDone?: () => void }) {
  const Icon = item.icon
  return (
    <a
      href={item.path}
      onClick={(e) => {
        e.preventDefault()
        navigate(item.path)
        onDone?.()
      }}
      aria-current={active ? 'page' : undefined}
      title={showLabel ? undefined : item.label}
      className={`group flex h-11 items-center gap-3 rounded-xl px-3 text-sm font-medium transition-colors ${
        active ? 'bg-ink-850 text-ink-100 shadow-sm ring-1 ring-lavender-200' : 'text-ink-300 hover:bg-ink-850/70 hover:text-ink-100'
      }`}
    >
      <span className={`grid h-7 w-7 shrink-0 place-items-center rounded-lg ${active ? 'bg-beacon-400 text-white' : 'text-ink-300 group-hover:text-beacon-300'}`}>
        <Icon size={18} />
      </span>
      <span className={`sm-motion truncate whitespace-nowrap transition-opacity duration-150 ${showLabel ? 'opacity-100' : 'opacity-0'}`}>{item.label}</span>
    </a>
  )
}

function statusOf(health: ApiState<Health>) {
  const { data, error, loading } = health
  const online = !error && data?.status === 'ok'
  const dot = loading && !data ? 'bg-ink-400' : online ? 'bg-safe' : 'bg-danger'
  const label = loading && !data ? 'Connecting…' : online ? 'Server online' : 'Server offline'
  return { dot, label, online }
}

function SystemStatus({ health, compact }: { health: ApiState<Health>; compact?: boolean }) {
  const { dot, label, online } = statusOf(health)
  const data = health.data
  if (compact) {
    return (
      <span className="grid h-11 place-items-center" role="status" title={label}>
        <span className={`h-2.5 w-2.5 rounded-full ${dot}`} />
        <span className="sr-only">{label}</span>
      </span>
    )
  }
  return (
    <div className="space-y-2 rounded-xl border border-ink-700 bg-ink-850 p-3 text-xs" role="status">
      <p className="flex items-center gap-2 font-medium text-ink-100">
        <span className={`h-2 w-2 rounded-full ${dot}`} />
        {label}
      </p>
      {data && online && (
        <dl className="space-y-1 text-ink-400">
          <div className="flex justify-between">
            <dt>Database</dt>
            <dd className={data.database === 'ok' ? 'text-safe-ink' : 'text-danger'}>{data.database === 'ok' ? 'OK' : 'Error'}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Vision AI key</dt>
            <dd className={data.gemini_configured ? 'text-safe-ink' : 'text-ink-300'}>{data.gemini_configured ? 'Configured' : 'Not set'}</dd>
          </div>
        </dl>
      )}
      {health.error && <p className="text-ink-400">Start the backend, then this page reconnects by itself.</p>}
    </div>
  )
}

function DemoBanner({ health }: { health: ApiState<Health> }) {
  if (!health.data?.demo_mode) return null
  return (
    <div className="border-b border-lavender-200 bg-lavender-50 px-4 py-1.5 text-center text-xs text-beacon-300">
      <strong className="font-semibold">Demo mode</strong> — shortened alert timers; help-call buttons ring a team member, never real
      emergency numbers.
    </div>
  )
}

/** Small city switcher. Switching reloads the page so every screen loads the new city's data. */
function CityPicker({ cities, onActive }: { cities: ApiState<CitiesInfo>; onActive?: (active: boolean) => void }) {
  const info = cities.data
  if (!info) return null
  const selected = currentCity() ?? info.default
  const walking = walkSession.get() != null
  return (
    <label className="block space-y-1 text-[11px] text-ink-400">
      <span>Demo area</span>
      <select
        value={selected}
        disabled={walking}
        title={walking ? 'End the walk before switching city' : 'Switch demo area'}
        onChange={(e) => switchCity(e.target.value)}
        onFocus={() => onActive?.(true)}
        onBlur={() => onActive?.(false)}
        className="w-full rounded-lg border border-ink-700 bg-ink-850 px-2 py-1.5 text-xs text-ink-100 disabled:opacity-60"
      >
        {info.cities.map((c) => (
          <option key={c.id} value={c.id}>
            {c.name}
            {c.has_map_data ? '' : ' (no map data yet)'}
          </option>
        ))}
      </select>
      {walking && <span className="block">End the walk before switching city.</span>}
    </label>
  )
}

export function cityName(info: CitiesInfo | null): string {
  if (!info) return ''
  const id = currentCity() ?? info.default
  return info.cities.find((c) => c.id === id)?.name ?? id
}

/** A button with a small popover panel that closes on outside click or Escape. */
function Popover({ label, button, children, width = 'w-72' }: { label: string; button: ReactNode; children: ReactNode; width?: string }) {
  const [open, setOpen] = useState(false)
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
  }, [open])
  return (
    <div ref={ref} className="relative">
      <button onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-label={label}
        className="relative grid h-10 w-10 place-items-center rounded-full text-ink-300 hover:bg-ink-800 hover:text-ink-100">
        {button}
      </button>
      {open && (
        <div className={`sm-card absolute top-12 right-0 z-[1400] ${width} p-3 text-sm`} role="dialog" aria-label={label}>
          {children}
        </div>
      )}
    </div>
  )
}

/** Only real states: a walk running on this device, the server being offline, demo mode. Nothing invented. */
function Notifications({ health }: { health: ApiState<Health> }) {
  const walking = walkSession.get()
  const offline = !!health.error
  const items: { tone: 'bad' | 'accent' | 'muted'; title: string; text: string; go?: string }[] = []
  if (walking) items.push({ tone: 'accent', title: 'Walk With Me is running', text: 'Your location is being shared on this device.', go: '/' })
  if (offline) items.push({ tone: 'bad', title: 'Server offline', text: 'Maps, routes and alerts reconnect by themselves when it is back.' })
  if (health.data?.demo_mode) items.push({ tone: 'muted', title: 'Demo mode', text: 'Shortened alert timers; help-call buttons ring a team member.' })
  return (
    <Popover label="Notifications" button={
      <>
        <BellIcon size={20} />
        {(walking || offline) && <span className="absolute top-2 right-2.5 h-2 w-2 rounded-full bg-danger ring-2 ring-ink-950" />}
      </>
    }>
      <p className="px-1 pb-2 text-xs font-semibold uppercase tracking-wider text-ink-400">Notifications</p>
      {items.length === 0 ? (
        <p className="px-1 py-2 text-ink-400">Nothing new.</p>
      ) : (
        <ul className="space-y-1">
          {items.map((n) => (
            <li key={n.title}>
              <button disabled={!n.go} onClick={() => n.go && navigate(n.go)}
                className="flex w-full gap-3 rounded-lg p-2 text-left enabled:hover:bg-ink-800">
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${n.tone === 'bad' ? 'bg-danger' : n.tone === 'accent' ? 'bg-beacon-400' : 'bg-ink-400'}`} />
                <span>
                  <span className="block font-medium text-ink-100">{n.title}</span>
                  <span className="block text-xs text-ink-400">{n.text}</span>
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </Popover>
  )
}

/** There are no user accounts: the "profile" is the name saved on this device for Walk With Me, if any. */
function Profile() {
  const name = savedProfile.get()?.walker_name?.trim()
  const initials = name ? name.split(/\s+/).map((w) => w[0]).slice(0, 2).join('').toUpperCase() : null
  return (
    <Popover label="Profile" button={
      <span className="grid h-9 w-9 place-items-center rounded-full bg-lavender-100 text-sm font-semibold text-beacon-300">
        {initials ?? <UserIcon size={18} />}
      </span>
    }>
      <div className="flex items-center gap-3 p-1">
        <span className="grid h-10 w-10 shrink-0 place-items-center rounded-full bg-lavender-100 font-semibold text-beacon-300">
          {initials ?? <UserIcon size={20} />}
        </span>
        <div className="min-w-0">
          <p className="truncate font-medium text-ink-100">{name ?? 'Guest'}</p>
          <p className="text-xs text-ink-400">This device</p>
        </div>
      </div>
      <p className="mt-2 rounded-lg bg-ink-900 p-2 text-xs text-ink-300">
        ShadowMap has no accounts. {name ? 'Your name and trusted contacts are saved only on this device, for Walk With Me.' : 'When you start Walk With Me, your name and contacts are saved only on this device.'}
      </p>
    </Popover>
  )
}

function Brand({ showText }: { showText: boolean }) {
  return (
    <a href="/" onClick={(e) => { e.preventDefault(); navigate('/') }} className="flex h-12 items-center gap-3 px-2">
      <span className="shrink-0"><LogoMark size={36} /></span>
      <span className={`sm-motion whitespace-nowrap transition-opacity duration-150 ${showText ? 'opacity-100' : 'opacity-0'}`}>
        <span className="block text-base font-bold tracking-wide text-ink-100">SHADOWMAP</span>
        <span className="block text-[11px] text-ink-400">Safer routes at night</span>
      </span>
    </a>
  )
}

function NavGroups({ active, showLabels, onDone }: { active: RouteName; showLabels: boolean; onDone?: () => void }) {
  return (
    <nav className="space-y-4" aria-label="Main">
      {GROUPS.map((g, i) => (
        <div key={g.title}>
          <div className="relative mb-1 h-5 px-3">
            <p className={`sm-motion absolute inset-x-3 text-[11px] font-semibold uppercase tracking-[0.14em] whitespace-nowrap text-ink-400 transition-opacity duration-150 ${showLabels ? 'opacity-100' : 'opacity-0'}`}>
              {g.title}
            </p>
            {i > 0 && <span className={`sm-motion absolute top-2 left-3 h-px w-7 bg-ink-600 transition-opacity ${showLabels ? 'opacity-0' : 'opacity-100'}`} />}
          </div>
          <div className="space-y-1">
            {g.items.map((item) => (
              <NavLink key={item.name} item={item} active={active === item.name} showLabel={showLabels} onDone={onDone} />
            ))}
          </div>
        </div>
      ))}
    </nav>
  )
}

export function AppShell({ active, children }: { active: RouteName; children: ReactNode }) {
  const health = useApi(api.health, 15000) // checked once here, shared by the status displays
  const cities = useApi(api.cities)
  const [expanded, setExpanded] = useState(false)
  const asideRef = useRef<HTMLElement>(null)
  const pinned = useRef(false) // the city list is open: a native dropdown counts as "outside", so do not collapse
  const [drawer, setDrawer] = useState(false)
  const [slot, setSlot] = useState<HTMLElement | null>(null)

  useEffect(() => {
    if (!drawer) return
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setDrawer(false)
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [drawer])

  return (
    <div className="min-h-full">
      {/* Sidebar — laptops. Floats over the page when expanded; the page itself keeps a fixed 76 px margin. */}
      <aside
        ref={asideRef}
        onMouseEnter={() => setExpanded(true)}
        onMouseLeave={() => !pinned.current && setExpanded(false)}
        onFocus={() => setExpanded(true)}
        onBlur={(e) => !e.currentTarget.contains(e.relatedTarget as Node) && setExpanded(false)}
        className={`sm-motion fixed inset-y-0 left-0 z-[1200] hidden flex-col overflow-hidden border-r border-lavender-200 bg-lavender-50 px-3 py-4 transition-[width,box-shadow] duration-200 ease-out lg:flex ${
          expanded ? `${EXPANDED} shadow-[8px_0_32px_rgb(28_32_64/0.12)]` : COLLAPSED
        }`}
      >
        <Brand showText={expanded} />
        <div className="mt-6 flex-1 overflow-y-auto overflow-x-hidden">
          <NavGroups active={active} showLabels={expanded} />
        </div>
        {expanded ? (
          <div className="w-[232px] space-y-3">
            <CityPicker cities={cities} onActive={(a) => {
              pinned.current = a
              if (!a && !asideRef.current?.matches(':hover')) setExpanded(false)
            }} />
            <SystemStatus health={health} />
            <p className="px-1 text-[11px] text-ink-400">Prototype · {cityName(cities.data) || 'demo'} area</p>
          </div>
        ) : (
          <div className="flex flex-col items-center gap-1 text-ink-400">
            <span className="grid h-11 place-items-center" title={`Demo area: ${cityName(cities.data)}`}><MapPinIcon size={18} /></span>
            <SystemStatus health={health} compact />
          </div>
        )}
      </aside>

      {/* Drawer — phones and tablets */}
      <div className={`fixed inset-0 z-[1300] lg:hidden ${drawer ? '' : 'pointer-events-none'}`} aria-hidden={!drawer}>
        <div onClick={() => setDrawer(false)} className={`sm-motion absolute inset-0 bg-ink-100/30 transition-opacity duration-200 ${drawer ? 'opacity-100' : 'opacity-0'}`} />
        <div role="dialog" aria-modal="true" aria-label="Menu"
          className={`sm-motion absolute inset-y-0 left-0 flex w-[min(86vw,300px)] flex-col bg-lavender-50 px-3 py-4 shadow-2xl transition-transform duration-200 ease-out ${drawer ? 'translate-x-0' : '-translate-x-full'}`}>
          <div className="flex items-center justify-between">
            <Brand showText />
            <button onClick={() => setDrawer(false)} aria-label="Close menu" className="grid h-10 w-10 place-items-center rounded-full text-ink-300 hover:bg-ink-850">
              <XIcon size={20} />
            </button>
          </div>
          <div className="mt-6 flex-1 overflow-y-auto">
            {drawer && <NavGroups active={active} showLabels onDone={() => setDrawer(false)} />}
          </div>
          <div className="space-y-3 pt-3">
            <CityPicker cities={cities} />
            <SystemStatus health={health} />
          </div>
        </div>
      </div>

      <div className="flex min-h-full min-w-0 flex-col lg:pl-[76px]">
        <header className="sticky top-0 z-[1100] border-b border-ink-700 bg-ink-900/90 backdrop-blur">
          <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-x-2 gap-y-2 px-4 py-2.5 sm:px-6 lg:px-10 lg:py-3">
            <button onClick={() => setDrawer(true)} aria-label="Open menu" aria-expanded={drawer}
              className="grid h-10 w-10 place-items-center rounded-full text-ink-300 hover:bg-ink-800 lg:hidden">
              <MenuIcon size={22} />
            </button>
            <span className="flex items-center gap-2 lg:hidden">
              <LogoMark size={28} />
              <span className="font-semibold tracking-tight">ShadowMap</span>
            </span>
            <div ref={setSlot} className="order-last w-full empty:hidden lg:order-none lg:w-auto lg:max-w-xl lg:flex-1" />
            <div className="ml-auto flex items-center gap-1">
              <Notifications health={health} />
              <Profile />
            </div>
          </div>
        </header>
        <DemoBanner health={health} />
        <TopBarSlotContext.Provider value={slot}>
          <main className="flex-1 px-4 pt-6 pb-10 sm:px-6 lg:px-10">{children}</main>
        </TopBarSlotContext.Provider>
      </div>
    </div>
  )
}
