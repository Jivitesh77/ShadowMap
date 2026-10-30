// Which map provider draws the background map. Change it without touching code by setting, in frontend/.env:
//   VITE_MAP_STYLE_URL=<a MapLibre style JSON address>
//   VITE_MAP_ATTRIBUTION=<the credit line that provider requires>
// The background map is only a picture. ShadowMap's own streets, scores, places and routes are drawn on top
// from our database, and routing never depends on the map provider.

export interface MapProvider {
  name: string
  styleUrl: string
  attribution: string
}

const OPENFREEMAP_DARK: MapProvider = {
  name: 'OpenFreeMap (dark)',
  styleUrl: 'https://tiles.openfreemap.org/styles/dark',
  attribution: '', // the OpenFreeMap style carries its own credit line (OpenFreeMap, OpenMapTiles, OpenStreetMap)
}

export const mapProvider: MapProvider = import.meta.env.VITE_MAP_STYLE_URL
  ? {
      name: 'Custom',
      styleUrl: import.meta.env.VITE_MAP_STYLE_URL,
      attribution: import.meta.env.VITE_MAP_ATTRIBUTION ?? '',
    }
  : OPENFREEMAP_DARK
