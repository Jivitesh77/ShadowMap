// Anonymous id for this browser, used only for rate limits and "one person cannot agree with themselves".
export function deviceId(): string {
  try {
    let id = localStorage.getItem('sm-device-id')
    if (!id) {
      id = crypto.randomUUID()
      localStorage.setItem('sm-device-id', id)
    }
    return id
  } catch {
    const w = window as unknown as { __smDevice?: string }
    w.__smDevice ??= 'session-' + Math.random().toString(36).slice(2, 12)
    return w.__smDevice
  }
}
