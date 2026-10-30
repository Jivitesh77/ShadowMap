// Which demo city this browser shows (IIIT Guwahati or Aastha Kunj, Delhi). Chosen once when the page loads:
// ?city=delhi in the address, else the last choice saved in this browser, else the server's default city.
// Switching reloads the page, so every map, score, place, report, route and dashboard is fetched for the new city.
const KEY = 'sm-city'

function initial(): string | null {
  try {
    const fromUrl = new URLSearchParams(window.location.search).get('city')
    if (fromUrl) return fromUrl
  } catch {
    /* no URL params */
  }
  try {
    return localStorage.getItem(KEY)
  } catch {
    return null // private mode: the server's default city is used
  }
}

const chosen = initial()

/** The chosen city id, or undefined to let the server use its default city. */
export function currentCity(): string | undefined {
  return chosen ?? undefined
}

export function switchCity(id: string) {
  try {
    localStorage.setItem(KEY, id)
  } catch {
    /* not saved: the address below still carries the choice for this load */
  }
  const url = new URL(window.location.href)
  url.searchParams.set('city', id)
  window.location.assign(url.toString())
}

/** Adds ?city=… (or &city=…) to a path. Uses the chosen city unless one is given; none = the server's default city. */
export function withCity(path: string, city: string | undefined = currentCity()): string {
  const c = city
  if (!c) return path
  return `${path}${path.includes('?') ? '&' : '?'}city=${encodeURIComponent(c)}`
}
