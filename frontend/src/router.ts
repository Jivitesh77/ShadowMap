// A tiny router: maps the browser address (e.g. /police) to a page, without an extra library.
import { useEffect, useState } from 'react'

export type RouteName = 'walker' | 'sentinel' | 'contact' | 'police' | 'city' | 'notfound'

export interface Route {
  name: RouteName
  params: { tripId?: string }
}

export function parsePath(path: string): Route {
  const clean = path.replace(/\/+$/, '') || '/'
  if (clean === '/') return { name: 'walker', params: {} }
  if (clean === '/sentinel') return { name: 'sentinel', params: {} }
  if (clean === '/trip') return { name: 'contact', params: {} }
  const trip = clean.match(/^\/trip\/([A-Za-z0-9-]+)$/)
  if (trip) return { name: 'contact', params: { tripId: trip[1] } }
  if (clean === '/police') return { name: 'police', params: {} }
  if (clean === '/city') return { name: 'city', params: {} }
  return { name: 'notfound', params: {} }
}

export function navigate(to: string) {
  if (to === window.location.pathname) return
  window.history.pushState({}, '', to)
  window.dispatchEvent(new PopStateEvent('popstate'))
  window.scrollTo(0, 0)
}

export function useRoute(): Route {
  const [route, setRoute] = useState(() => parsePath(window.location.pathname))
  useEffect(() => {
    const onChange = () => setRoute(parsePath(window.location.pathname))
    window.addEventListener('popstate', onChange)
    return () => window.removeEventListener('popstate', onChange)
  }, [])
  return route
}
