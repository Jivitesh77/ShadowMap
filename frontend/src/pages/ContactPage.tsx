import { UsersIcon } from '../components/Icons'
import { EmptyState } from '../components/States'
import { InDevelopment, PageHeader, Panel } from '../components/Ui'

export default function ContactPage({ tripId }: { tripId?: string }) {
  return (
    <div className="mx-auto max-w-4xl space-y-6">
      <PageHeader
        eyebrow="Trusted contact"
        title={tripId ? 'Live trip' : 'Follow a walk'}
        description="When someone adds you as a trusted contact, their trip link shows their live position, planned route and expected arrival, and alerts you if they stop responding."
      />
      <Panel>
        {tripId ? (
          <EmptyState
            icon={<UsersIcon size={22} />}
            title="This trip can't be shown yet"
            action={<InDevelopment>Arrives with Walk With Me</InDevelopment>}
          >
            <span className="break-all">Trip link: {tripId}</span>
            <br />
            Live trip tracking is not part of this build yet.
          </EmptyState>
        ) : (
          <EmptyState icon={<UsersIcon size={22} />} title="No trip open">
            Open the trip link the walker shared with you. It looks like <span className="text-ink-300">/trip/…</span> and works
            without installing anything.
          </EmptyState>
        )}
      </Panel>
      <p className="text-center text-xs text-ink-400">
        Location is shared only during a walk the person started, only with people they chose, and stops on arrival.
      </p>
    </div>
  )
}
