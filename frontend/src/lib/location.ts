// The phone's current position, with plain-language errors.
import type { LatLon } from '../api'

export function getMyLocation(): Promise<LatLon> {
  return new Promise((resolve, reject) => {
    if (!window.isSecureContext) return reject(new Error('Your location only works on a secure (https) page. Tap the map instead.'))
    if (!('geolocation' in navigator)) return reject(new Error('This browser cannot read your location. Tap the map instead.'))
    navigator.geolocation.getCurrentPosition(
      (p) => resolve({ lat: p.coords.latitude, lon: p.coords.longitude }),
      (err) =>
        reject(
          new Error(
            err.code === err.PERMISSION_DENIED
              ? 'Location permission was refused. Allow it in your browser settings, or tap the map instead.'
              : 'Your position could not be found. Tap the map instead.',
          ),
        ),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 30000 },
    )
  })
}
