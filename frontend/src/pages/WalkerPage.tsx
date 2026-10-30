import { api } from '../api'
import { useApi } from '../hooks/useApi'
import { MapPinIcon } from '../components/Icons'
import { EmptyState, ErrorState } from '../components/States'
import { InDevelopment, PageHeader, Panel, Stat } from '../components/Ui'

export default function WalkerPage() {
  const summary = useApi(api.summary)
  const s = summary.data

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader
        eyebrow="Walker"
        title="Plan a safer walk"
        description="Compare the shortest and the safest route, built from street photos taken by riders in the last hours and places open at the time of your walk."
      />

      <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
        <div className="min-h-[420px] rounded-2xl border border-ink-700 bg-ink-850 bg-[radial-gradient(circle_at_1px_1px,var(--color-ink-700)_1px,transparent_0)] bg-[size:22px_22px] p-6 lg:min-h-[560px]">
          <div className="flex h-full items-center justify-center">
            <EmptyState
              icon={<MapPinIcon size={22} />}
              title="Street map not loaded yet"
              action={<InDevelopment>Next build step: map data</InDevelopment>}
            >
              The map of IIIT Guwahati and its surrounding streets appears here once OpenStreetMap data has been
              imported.
            </EmptyState>
          </div>
        </div>

        <div className="space-y-6">
          <Panel title="Map coverage">
            {summary.error ? (
              <ErrorState message={summary.error} onRetry={summary.reload} />
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Street segments" value={s?.streets} loading={summary.loading} />
                <Stat label="Safe places" value={s?.places} loading={summary.loading} />
                <Stat label="Street photos" value={s?.observations} loading={summary.loading} />
                <Stat label="Community reports" value={s?.reports} loading={summary.loading} />
              </div>
            )}
          </Panel>

          <Panel title="How routes are chosen">
            <ul className="space-y-3 text-sm text-ink-300">
              <li className="flex gap-3">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-safe" />
                Lit streets with people around and places open nearby score highest.
              </li>
              <li className="flex gap-3">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-caution" />
                Recent photos count most; older information fades back to map data.
              </li>
              <li className="flex gap-3">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full bg-danger" />
                The safest route is never more than 50% longer than the shortest.
              </li>
            </ul>
            <p className="mt-4 border-t border-ink-700 pt-3 text-xs text-ink-400">
              ShadowMap describes street conditions. It never promises that a route is safe.
            </p>
          </Panel>
        </div>
      </div>
    </div>
  )
}
