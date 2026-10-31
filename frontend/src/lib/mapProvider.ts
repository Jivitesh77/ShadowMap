// Background map tiles for the Leaflet map. Default: OpenStreetMap's standard tiles.
// To use another tile server without code changes, set in frontend/.env:
//   VITE_TILE_URL=<tile address with {z}/{x}/{y}>
//   VITE_TILE_ATTRIBUTION=<credit line the provider requires>
// Tiles are only a picture: streets, scores, places and routes come from ShadowMap's own data,
// and routing runs in the backend, independent of the map.
// Never point this at Google tiles: Google content may only be shown on Google's own map.

export interface TileProvider {
  name: string
  url: string
  attribution: string
}

const OSM_STANDARD: TileProvider = {
  name: 'OpenStreetMap',
  url: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
  attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
}

// OpenStreetMap refuses tiles without a Referer, and the page itself sends none (no-referrer). Every map's tiles send only
// the site's address — never the page path, which can hold a trip link. Use on EVERY <TileLayer>.
export const tileReferrerPolicy = 'strict-origin' as const

export const tileProvider: TileProvider = import.meta.env.VITE_TILE_URL
  ? { name: 'Custom', url: import.meta.env.VITE_TILE_URL, attribution: import.meta.env.VITE_TILE_ATTRIBUTION ?? '' }
  : OSM_STANDARD
