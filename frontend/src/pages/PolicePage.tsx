import { api } from '../api'
import { useApi } from '../hooks/useApi'
import { InfoIcon, ShieldIcon } from '../components/Icons'
import { EmptyState, ErrorState, LoadingBlock } from '../components/States'
import { Badge, PageHeader, Panel, Stat } from '../components/Ui'

export default function PolicePage() {
  const summary = useApi(api.summary, 10000)
  const s = summary.data

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Police control room"
        description="Live alerts from walkers who did not answer “Are you safe?” or pressed SOS, with their position, route and the latest street photo."
        aside={<Badge tone="warn">Simulated — not connected to any police system</Badge>}
      />

      {summary.error ? (
        <ErrorState message={summary.error} onRetry={summary.reload} />
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Open alerts" value={s?.open_alerts} loading={summary.loading} />
          <Stat label="Active walks" value={s?.active_walks} loading={summary.loading} />
          <Stat label="All alerts" value={s?.alerts} loading={summary.loading} />
          <Stat label="Street photos" value={s?.observations} loading={summary.loading} />
        </div>
      )}

      <div className="grid gap-6 lg:grid-cols-[1fr_360px]">
        <Panel title="Live alerts">
          {summary.error ? (
            <EmptyState icon={<ShieldIcon size={22} />} title="Can't check for alerts">
              The server is unreachable, so alerts cannot be shown. This does not mean there are none.
            </EmptyState>
          ) : summary.loading && !s ? (
            <LoadingBlock label="Loading alerts…" />
          ) : (
            <EmptyState icon={<ShieldIcon size={22} />} title="No alerts">
              Alerts appear here, newest first, when a walker does not respond to a safety check or presses SOS.
            </EmptyState>
          )}
        </Panel>
        <Panel title="Status workflow">
          <ol className="space-y-3 text-sm">
            {['New', 'Acknowledged', 'Unit sent', 'Resolved'].map((step, i) => (
              <li key={step} className="flex items-center gap-3">
                <span className="grid h-6 w-6 place-items-center rounded-full bg-ink-700 text-xs font-semibold text-ink-300">
                  {i + 1}
                </span>
                <span className="text-ink-100">{step}</span>
              </li>
            ))}
          </ol>
          <p className="mt-4 flex gap-2 border-t border-ink-700 pt-3 text-xs text-ink-400">
            <InfoIcon size={16} className="shrink-0" />
            Positions are visible only while an alert is open. Nobody is tracked otherwise.
          </p>
        </Panel>
      </div>
    </div>
  )
}
