// Shared loading, error and empty displays, so every screen handles these the same way.
import type { ReactNode } from 'react'
import { AlertIcon, RefreshIcon } from './Icons'

export function Skeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`relative overflow-hidden rounded-md bg-ink-800 ${className}`} aria-hidden="true">
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_1.6s_infinite] bg-gradient-to-r from-transparent via-ink-700/60 to-transparent" />
    </div>
  )
}

export function LoadingBlock({ label = 'Loading…', rows = 3 }: { label?: string; rows?: number }) {
  return (
    <div role="status" aria-live="polite" className="space-y-3">
      <span className="sr-only">{label}</span>
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className={i === 0 ? 'h-5 w-2/5' : 'h-4 w-full'} />
      ))}
    </div>
  )
}

export function ErrorState({ message, onRetry, title = 'Something went wrong' }: { message: string; onRetry?: () => void; title?: string }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-danger/30 bg-danger/10 p-4">
      <AlertIcon className="mt-0.5 shrink-0 text-danger" />
      <div className="flex-1">
        <p className="text-sm font-semibold text-ink-100">{title}</p>
        <p className="mt-1 text-sm text-ink-300">{message}</p>
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-ink-600 px-3 py-1.5 text-sm font-medium text-ink-100 hover:bg-ink-700"
        >
          <RefreshIcon size={16} /> Retry
        </button>
      )}
    </div>
  )
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon: ReactNode
  title: string
  children?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-ink-600 px-6 py-10 text-center">
      <div className="mb-3 grid h-12 w-12 place-items-center rounded-full bg-ink-800 text-ink-300">{icon}</div>
      <p className="font-semibold text-ink-100">{title}</p>
      {children && <div className="mt-1.5 max-w-md text-sm text-ink-400">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
