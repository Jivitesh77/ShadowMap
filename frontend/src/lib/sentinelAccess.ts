// The Sentinel access code (set by the team in backend/.env). Kept in this browser so it is asked for only once.
let memory: string | null = null

export function getAccessCode(): string | null {
  try {
    return localStorage.getItem('sm-sentinel-code') ?? memory
  } catch {
    return memory
  }
}

export function setAccessCode(code: string | null) {
  memory = code
  try {
    if (code) localStorage.setItem('sm-sentinel-code', code)
    else localStorage.removeItem('sm-sentinel-code')
  } catch {
    /* private mode: keep it in memory for this visit */
  }
}

export function accessHeaders(): Record<string, string> {
  const code = getAccessCode()
  return code ? { 'X-Sentinel-Token': code } : {}
}
