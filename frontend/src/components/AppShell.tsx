// The frame around every page: sidebar on large screens, top bar + bottom tabs on phones.
import type { ReactNode } from 'react'
import { api, type Health } from '../api'
import { useApi, type ApiState } from '../hooks/useApi'
import { navigate, type RouteName } from '../router'
import { BuildingIcon, CameraIcon, LogoMark, RouteIcon, ShieldIcon, UsersIcon } from './Icons'

interface NavItem {
  name: RouteName
  label: string
  short: string
  path: string
  icon: (p: { size?: number }) => ReactNode
  group: 'Public' | 'Operations'
}

const NAV: NavItem[] = [
  { name: 'walker', label: 'Walker', short: 'Walk', path: '/', icon: RouteIcon, group: 'Public' },
  { name: 'sentinel', label: 'Sentinel', short: 'Sentinel', path: '/sentinel', icon: CameraIcon, group: 'Public' },
  { name: 'contact', label: 'Trusted contact', short: 'Contact', path: '/trip', icon: UsersIcon, group: 'Public' },
  { name: 'police', label: 'Police control room', short: 'Police', path: '/police', icon: ShieldIcon, group: 'Operations' },
  { name: 'city', label: 'City dashboard', short: 'City', path: '/city', icon: BuildingIcon, group: 'Operations' },
]

function NavLink({ item, active, compact }: { item: NavItem; active: boolean; compact?: boolean }) {
  const Icon = item.icon
  return (
    <a
      href={item.path}
      onClick={(e) => {
        e.preventDefault()
        navigate(item.path)
      }}
      aria-current={active ? 'page' : undefined}
      className={
        compact
          ? `flex flex-1 flex-col items-center gap-1 py-2 text-[11px] font-medium ${active ? 'text-beacon-400' : 'text-ink-400'}`
          : `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
              active ? 'bg-ink-700 text-ink-100' : 'text-ink-300 hover:bg-ink-800 hover:text-ink-100'
            }`
      }
    >
      <span className={!compact && active ? 'text-beacon-400' : undefined}>
        <Icon size={compact ? 22 : 18} />
      </span>
      {compact ? item.short : item.label}
    </a>
  )
}

function SystemStatus({ health, compact }: { health: ApiState<Health>; compact?: boolean }) {
  const { data, error, loading } = health
  const online = !error && data?.status === 'ok'
  const dot = loading && !data ? 'bg-ink-400' : online ? 'bg-safe' : 'bg-danger'
  const label = loading && !data ? 'Connecting…' : online ? 'Server online' : 'Server offline'

  if (compact) {
    return (
      <span className="inline-flex items-center gap-2 text-xs text-ink-300" role="status">
        <span className={`h-2 w-2 rounded-full ${dot}`} />
        {label}
      </span>
    )
  }
  return (
    <div className="space-y-2 rounded-xl border border-ink-700 bg-ink-900/60 p-3 text-xs" role="status">
      <p className="flex items-center gap-2 font-medium text-ink-100">
        <span className={`h-2 w-2 rounded-full ${dot}`} />
        {label}
      </p>
      {data && online && (
        <dl className="space-y-1 text-ink-400">
          <div className="flex justify-between">
            <dt>Database</dt>
            <dd className={data.database === 'ok' ? 'text-safe' : 'text-danger'}>{data.database === 'ok' ? 'OK' : 'Error'}</dd>
          </div>
          <div className="flex justify-between">
            <dt>Vision AI key</dt>
            <dd className={data.gemini_configured ? 'text-safe' : 'text-ink-300'}>
              {data.gemini_configured ? 'Configured' : 'Not set'}
            </dd>
          </div>
        </dl>
      )}
      {error && <p className="text-ink-400">Start the backend, then this page reconnects by itself.</p>}
    </div>
  )
}

function DemoBanner({ health }: { health: ApiState<Health> }) {
  if (!health.data?.demo_mode) return null
  return (
    <div className="border-b border-beacon-400/20 bg-beacon-400/10 px-4 py-1.5 text-center text-xs text-beacon-300">
      <strong className="font-semibold">Demo mode</strong> — shortened alert timers; help-call buttons ring a team member, never real
      emergency numbers.
    </div>
  )
}

export function AppShell({ active, children }: { active: RouteName; children: ReactNode }) {
  const groups = ['Public', 'Operations'] as const
  const health = useApi(api.health, 15000) // checked once here, shared by the status displays
  return (
    <div className="flex min-h-full">
      {/* Sidebar — laptops and tablets */}
      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-ink-700 bg-ink-950 px-4 py-5 lg:flex">
        <a
          href="/"
          onClick={(e) => {
            e.preventDefault()
            navigate('/')
          }}
          className="flex items-center gap-2.5 px-2"
        >
          <LogoMark />
          <span>
            <span className="block text-base font-semibold tracking-tight">ShadowMap</span>
            <span className="block text-[11px] text-ink-400">Safer routes at night</span>
          </span>
        </a>
        <nav className="mt-8 flex-1 space-y-6" aria-label="Main">
          {groups.map((g) => (
            <div key={g}>
              <p className="px-3 pb-2 text-[11px] font-semibold uppercase tracking-[0.14em] text-ink-400">{g}</p>
              <div className="space-y-1">
                {NAV.filter((n) => n.group === g).map((item) => (
                  <NavLink key={item.name} item={item} active={active === item.name} />
                ))}
              </div>
            </div>
          ))}
        </nav>
        <SystemStatus health={health} />
        <p className="mt-3 px-1 text-[11px] text-ink-400">Prototype · IIIT Guwahati area</p>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar — phones */}
        <header className="sticky top-0 z-20 flex items-center justify-between border-b border-ink-700 bg-ink-950/95 px-4 py-3 backdrop-blur lg:hidden">
          <span className="flex items-center gap-2">
            <LogoMark size={26} />
            <span className="font-semibold tracking-tight">ShadowMap</span>
          </span>
          <SystemStatus health={health} compact />
        </header>
        <DemoBanner health={health} />
        <main className="flex-1 px-4 pt-6 pb-28 sm:px-6 lg:px-10 lg:pb-10">{children}</main>
      </div>

      {/* Bottom tabs — phones */}
      <nav
        aria-label="Main"
        className="fixed inset-x-0 bottom-0 z-20 flex border-t border-ink-700 bg-ink-950/95 pb-[env(safe-area-inset-bottom)] backdrop-blur lg:hidden"
      >
        {NAV.map((item) => (
          <NavLink key={item.name} item={item} active={active === item.name} compact />
        ))}
      </nav>
    </div>
  )
}
