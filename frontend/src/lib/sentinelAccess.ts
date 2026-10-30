// The Sentinel access code (set by the team in backend/.env). Kept for this browser tab's session only (lib/accessCodes.ts).
import { getCode, setCode } from './accessCodes'

export function getAccessCode(): string | null {
  return getCode('sentinel')
}

export function setAccessCode(code: string | null) {
  setCode('sentinel', code)
}

export function accessHeaders(): Record<string, string> {
  const code = getAccessCode()
  return code ? { 'X-Sentinel-Token': code } : {}
}
