import { AppShell } from './components/AppShell'
import { MapPinIcon } from './components/Icons'
import { EmptyState } from './components/States'
import { navigate, useRoute } from './router'
import CityPage from './pages/CityPage'
import ContactPage from './pages/ContactPage'
import PolicePage from './pages/PolicePage'
import SentinelPage from './pages/SentinelPage'
import WalkerPage from './pages/WalkerPage'

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

  return <AppShell active={route.name}>{page}</AppShell>
}
