// Small building blocks used across pages.
import type { ReactNode } from 'react'
import { Skeleton } from './States'

export function PageHeader({
  eyebrow,
  title,
  description,
  aside,
}: {
  eyebrow: string
  title: string
  description: string
  aside?: ReactNode
}) {
  return (
    <header className="flex flex-col gap-4 border-b border-ink-700 pb-5 sm:flex-row sm:items-end sm:justify-between">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.14em] text-beacon-400">{eyebrow}</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink-100 sm:text-3xl">{title}</h1>
        <p className="mt-1.5 max-w-2xl text-sm text-ink-300">{description}</p>
      </div>
      {aside}
    </header>
  )
}

export function Panel({ title, children, className = '' }: { title?: string; children: ReactNode; className?: string }) {
  return (
    <section className={`rounded-2xl border border-ink-700 bg-ink-850 p-5 ${className}`}>
      {title && <h2 className="mb-4 text-sm font-semibold uppercase tracking-wider text-ink-300">{title}</h2>}
      {children}
    </section>
  )
}

/** A number taken from the backend. Shows a skeleton while loading and a dash on error — never a made-up value. */
export function Stat({
  label,
  value,
  loading,
  hint,
}: {
  label: string
  value: number | null | undefined
  loading: boolean
  hint?: string
}) {
  return (
    <div className="rounded-xl border border-ink-700 bg-ink-900/60 p-4">
      <p className="text-xs font-medium text-ink-400">{label}</p>
      {loading ? (
        <Skeleton className="mt-2 h-7 w-12" />
      ) : (
        <p className="mt-1 text-2xl font-semibold tabular-nums text-ink-100">{value ?? '—'}</p>
      )}
      {hint && <p className="mt-1 text-xs text-ink-400">{hint}</p>}
    </div>
  )
}

export function Badge({ tone, children }: { tone: 'ok' | 'warn' | 'bad' | 'neutral' | 'beacon'; children: ReactNode }) {
  const tones = {
    ok: 'bg-safe/15 text-safe-ink ring-safe/30',
    warn: 'bg-caution/15 text-caution-ink ring-caution/30',
    bad: 'bg-danger/15 text-danger ring-danger/30',
    neutral: 'bg-ink-700 text-ink-300 ring-ink-600',
    beacon: 'bg-beacon-400/15 text-beacon-300 ring-beacon-400/30',
  }
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset ${tones[tone]}`}>
      {children}
    </span>
  )
}

export function InDevelopment({ children }: { children: ReactNode }) {
  return (
    <p className="inline-flex items-center gap-2 rounded-lg bg-ink-800 px-3 py-2 text-xs text-ink-300">
      <span className="h-1.5 w-1.5 rounded-full bg-beacon-400" />
      {children}
    </p>
  )
}
