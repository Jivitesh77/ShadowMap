// Labels, icons and styles for map items. Green / yellow / red are kept for safety scores only.
import type { Place, RoadClass, SafetyColour, StatusBasis } from '../api'

export interface CategoryMeta {
  label: string
  plural: string
  icon: string // inner SVG markup, 24x24 stroke icon
}

export const CATEGORIES: Record<string, CategoryMeta> = {
  police: {
    label: 'Police',
    plural: 'Police',
    icon: '<path d="M12 3l8 3v6c0 4.6-3.3 8.3-8 9-4.7-.7-8-4.4-8-9V6l8-3z"/>',
  },
  hospital: { label: 'Hospital', plural: 'Hospitals', icon: '<path d="M12 6v12M6 12h12"/>' },
  clinic: {
    label: 'Clinic',
    plural: 'Clinics',
    icon: '<rect x="4" y="4" width="16" height="16" rx="3"/><path d="M12 8v8M8 12h8"/>',
  },
  pharmacy: {
    label: 'Pharmacy',
    plural: 'Pharmacies',
    icon: '<rect x="3" y="9" width="18" height="7" rx="3.5" transform="rotate(-45 12 12.5)"/><path d="M9.5 10l5 5"/>',
  },
  fuel: {
    label: 'Petrol pump',
    plural: 'Petrol pumps',
    icon: '<path d="M5 20V5a1 1 0 0 1 1-1h7a1 1 0 0 1 1 1v15M4 20h11M5 10h9M14 9l3 2v6a1.5 1.5 0 0 0 3 0V8l-3-3"/>',
  },
  atm: {
    label: 'ATM',
    plural: 'ATMs',
    icon: '<rect x="3" y="6" width="18" height="12" rx="2"/><circle cx="12" cy="12" r="2.5"/>',
  },
  transit: {
    label: 'Bus / train stop',
    plural: 'Transit stops',
    icon: '<rect x="5" y="4" width="14" height="13" rx="2"/><path d="M5 11h14M8 20v-3M16 20v-3"/>',
  },
  food_shop: {
    label: 'Shop / food',
    plural: 'Shops & food',
    icon: '<path d="M5 8h14l-1 12H6L5 8zM9 8V6a3 3 0 0 1 6 0v2"/>',
  },
  hotel: { label: 'Hotel', plural: 'Hotels', icon: '<path d="M3 18V7M3 14h18v4M21 14v-2a3 3 0 0 0-3-3h-7v5"/><circle cx="7" cy="11" r="1.5"/>' },
}

export const CATEGORY_ORDER = ['police', 'hospital', 'clinic', 'pharmacy', 'fuel', 'atm', 'transit', 'food_shop', 'hotel']

export function categoryMeta(cat: string): CategoryMeta {
  return CATEGORIES[cat] ?? { label: cat, plural: cat, icon: '<circle cx="12" cy="12" r="4"/>' }
}

export function placeName(p: Place): string {
  return p.name || `Unnamed ${categoryMeta(p.category).label.toLowerCase()}`
}

export const STATUS_LABEL = { open: 'Open', closed: 'Closed', unknown: 'Hours unknown' } as const

const USUALLY_24H = new Set(['police', 'hospital', 'hotel'])

export function statusExplanation(p: Pick<Place, 'status' | 'status_basis' | 'opening_hours' | 'category'>): string {
  const map: Record<StatusBasis, string> = {
    listed: `Based on the listed hours: ${p.opening_hours}`,
    missing: USUALLY_24H.has(p.category)
      ? 'No opening hours are listed. Places of this type are often open 24 hours, but that is not confirmed — treat as unknown.'
      : 'No opening hours are listed for this place.',
    unreadable: `Hours are listed (“${p.opening_hours}”) but in a format ShadowMap cannot read yet.`,
  }
  return map[p.status_basis]
}

export const ROAD_CLASS: Record<RoadClass, { label: string; color: string; weight: number; dash?: string }> = {
  main: { label: 'Main road', color: '#d6deeb', weight: 5 },
  residential: { label: 'Residential street', color: '#8b9bb8', weight: 3.5 },
  lane: { label: 'Lane or footpath', color: '#6a7a98', weight: 2.5, dash: '6 5' },
  underpass: { label: 'Underpass', color: '#6a7a98', weight: 3, dash: '2 6' },
}

const ROAD_TYPE: Record<string, string> = {
  trunk: 'National highway',
  trunk_link: 'Highway slip road',
  primary: 'Primary road',
  secondary: 'Secondary road',
  tertiary: 'Tertiary road',
  unclassified: 'Minor road',
  residential: 'Residential street',
  service: 'Service road',
  footway: 'Footpath',
  path: 'Path',
  track: 'Track',
}

export function roadTypeLabel(t: string): string {
  return ROAD_TYPE[t] ?? t.replace(/_/g, ' ')
}

export function formatDistance(m: number): string {
  return m < 1000 ? `${Math.round(m)} m` : `${(m / 1000).toFixed(1)} km`
}

export function osmUrl(osmId: string | null): string | null {
  return osmId ? `https://www.openstreetmap.org/${osmId}` : null
}

// Street safety colours (blueprint §7): 70-100 green, 40-69 yellow, 0-39 red.
export const SAFETY_COLOURS: Record<SafetyColour, string> = { green: '#22c55e', yellow: '#eab308', red: '#ef4444' }
export const SAFETY_LABEL: Record<SafetyColour, string> = {
  green: 'Green (70–100): lit, people around, open places nearby',
  yellow: 'Yellow (40–69): some concerns; fine if nothing better',
  red: 'Red (0–39): dark, empty or isolated; avoid at night',
}

export function formatAge(minutes: number | null | undefined): string {
  if (minutes == null) return 'Map data only'
  if (minutes < 1) return 'Seen just now'
  if (minutes < 60) return `Seen ${Math.round(minutes)} min ago`
  return `Seen ${Math.floor(minutes / 60)} h ${Math.round(minutes % 60)} min ago`
}
