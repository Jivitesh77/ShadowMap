// Access codes for the team screens (Police control room, Sentinel), set by the team in backend/.env.
// Kept only for this browser tab's session (sessionStorage): a page refresh keeps you signed in, closing the tab or the
// browser signs you out. Each screen has its own code, so signing out of one never signs out of the other.
// Codes only travel in request headers (X-Police-Token / X-Sentinel-Token) — never in URLs, messages or the console.
export type CodeKind = 'police' | 'sentinel'

const KEYS: Record<CodeKind, string> = { police: 'sm-police-code', sentinel: 'sm-sentinel-code' }
const memory: Record<CodeKind, string | null> = { police: null, sentinel: null } // when the browser blocks storage
export const ACCESS_CHANGED = 'sm-access-changed' // window event, detail = CodeKind

/** Earlier versions kept the codes in localStorage (kept after closing the browser). Move such a code into this session
 *  once, so nobody is signed out mid-shift, and delete the persistent copy. */
function dropPersistentCopy(kind: CodeKind) {
  try {
    const old = localStorage.getItem(KEYS[kind])
    if (old === null) return
    localStorage.removeItem(KEYS[kind])
    try {
      if (!sessionStorage.getItem(KEYS[kind])) sessionStorage.setItem(KEYS[kind], old)
    } catch {
      memory[kind] = memory[kind] ?? old
    }
  } catch {
    /* storage blocked: nothing persistent to remove */
  }
}

export function getCode(kind: CodeKind): string | null {
  dropPersistentCopy(kind)
  try {
    return sessionStorage.getItem(KEYS[kind]) ?? memory[kind]
  } catch {
    return memory[kind]
  }
}

/** Store a code for this session, or sign out with null. Tells the open screens (ACCESS_CHANGED). */
export function setCode(kind: CodeKind, code: string | null) {
  memory[kind] = code
  try {
    if (code) sessionStorage.setItem(KEYS[kind], code)
    else sessionStorage.removeItem(KEYS[kind])
  } catch {
    /* private mode: kept in memory for this page only */
  }
  try {
    localStorage.removeItem(KEYS[kind])
  } catch {
    /* nothing to remove */
  }
  window.dispatchEvent(new CustomEvent(ACCESS_CHANGED, { detail: kind }))
}

/** True for the server's "no / wrong access code" answers (401 / 403 with these codes). */
export function isAccessRefusal(status: number | undefined, code: string | undefined) {
  return (status === 401 || status === 403) && (code === 'access_code_required' || code === 'access_code_wrong')
}
