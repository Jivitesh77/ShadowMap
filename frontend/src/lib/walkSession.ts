// The walk running on this phone, and the contacts saved for next time (blueprint §9: "saved once").
// Stored only in this browser. The walk token is the walker's private key: it never goes into a link.
export interface WalkSession {
  walk_id: string
  token: string
  walker_name: string
  contact_path: string
  simulated: boolean
}

function read<T>(key: string): T | null {
  try {
    const v = localStorage.getItem(key)
    return v ? (JSON.parse(v) as T) : null
  } catch {
    return null
  }
}

function write(key: string, value: unknown) {
  try {
    if (value == null) localStorage.removeItem(key)
    else localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* private mode: the walk still runs while this page stays open */
  }
}

export const walkSession = {
  get: () => read<WalkSession>('sm-walk'),
  set: (s: WalkSession | null) => write('sm-walk', s),
}

export interface SavedProfile {
  walker_name: string
  walker_phone: string
  contacts: { name: string; phone: string }[]
}

export const savedProfile = {
  get: () => read<SavedProfile>('sm-walk-profile'),
  set: (p: SavedProfile) => write('sm-walk-profile', p),
}
