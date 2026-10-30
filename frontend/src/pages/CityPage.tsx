import { api } from '../api'
import { useApi } from '../hooks/useApi'
import { LightbulbIcon } from '../components/Icons'
import { EmptyState, ErrorState, LoadingBlock } from '../components/States'
import { PageHeader, Panel, Stat } from '../components/Ui'

export default function CityPage() {
  const summary = useApi(api.summary, 30000)
  const s = summary.data

  return (
    <div className="mx-auto max-w-7xl space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="City dashboard"
        description="Dark streets and broken streetlights, with photo evidence, ranked by how many people walk through them, so repairs help the most people first."
      />

      {summary.error ? (
        <ErrorState message={summary.error} onRetry={summary.reload} />
      ) : (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3">
          <Stat label="Street segments mapped" value={s?.streets} loading={summary.loading} />
          <Stat label="Street photos analysed" value={s?.observations} loading={summary.loading} />
          <Stat label="Community reports" value={s?.reports} loading={summary.loading} />
        </div>
      )}

      <Panel title="Streetlight repair list">
        {summary.error ? (
          <EmptyState icon={<LightbulbIcon size={22} />} title="Can't load the repair list">
            The server is unreachable. Try again once it is running.
          </EmptyState>
        ) : summary.loading && !s ? (
          <LoadingBlock label="Loading repair list…" />
        ) : (
          <EmptyState icon={<LightbulbIcon size={22} />} title="No repairs to rank yet">
            Streets appear here once Sentinel photos show broken or missing lights, or people report a broken streetlight.
          </EmptyState>
        )}
      </Panel>
    </div>
  )
}
