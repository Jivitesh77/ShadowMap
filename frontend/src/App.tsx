import { lazy, Suspense } from 'react'
import { AppShell } from './components/AppShell'
import { MapPinIcon } from './components/Icons'
import { EmptyState, LoadingBlock } from './components/States'
import { navigate, useRoute } from './router'

// Each screen is loaded when it is first opened, so the first page appears sooner (smaller start-up download).
const CityPage = lazy(() => import('./pages/CityPage'))
const ContactPage = lazy(() => import('./pages/ContactPage'))
const PolicePage = lazy(() => import('./pages/PolicePage'))
const SentinelPage = lazy(() => import('./pages/SentinelPage'))
const WalkerPage = lazy(() => import('./pages/WalkerPage'))

export default function App() {
  const route = useRoute()

  let page
  switch (route.name) {
    case 'walker':
      page = <WalkerPage />
      break
    case 'sentinel':
      page = <SentinelPage />
      break
    case 'contact':
      page = <ContactPage tripId={route.params.tripId} />
      break
    case 'police':
      page = <PolicePage />
      break
    case 'city':
      page = <CityPage />
      break
    default:
      page = (
        <div className="mx-auto max-w-lg pt-16">
          <EmptyState
            icon={<MapPinIcon size={22} />}
            title="Page not found"
            action={
              <button onClick={() => navigate('/')} className="rounded-lg bg-beacon-400 px-4 py-2 text-sm font-semibold text-ink-950">
                Go to the map
              </button>
            }
          >
            This address doesn't match any ShadowMap screen.
          </EmptyState>
        </div>
      )
  }

  return (
    <AppShell active={route.name}>
      <Suspense fallback={<div className="mx-auto max-w-3xl pt-6"><LoadingBlock label="Loading the page…" /></div>}>{page}</Suspense>
    </AppShell>
  )
}
