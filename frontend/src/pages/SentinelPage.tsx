import { CameraIcon, CheckIcon, XIcon } from '../components/Icons'
import { Badge, InDevelopment, PageHeader, Panel } from '../components/Ui'

// Real checks of what this browser allows. Phones only allow camera and GPS on secure (https) pages.
function deviceChecks() {
  return [
    {
      label: 'Secure connection',
      ok: window.isSecureContext,
      help: 'Camera and GPS only work on https pages (or on localhost).',
    },
    { label: 'Camera access', ok: !!navigator.mediaDevices?.getUserMedia, help: 'This browser cannot open the camera here.' },
    { label: 'GPS location', ok: 'geolocation' in navigator, help: 'This browser cannot read location.' },
  ]
}

const RULES = [
  ['Photo interval', 'Every 5 to 10 seconds'],
  ['Only while moving', 'Above about 5 km/h'],
  ['Skip duplicates', 'No new photo within about 30 m'],
  ['Hours', '6 pm to 6 am by default'],
  ['Photo size', 'About 640 pixels wide'],
  ['Photo storage', 'Deleted after 6 hours; faces and plates blurred'],
]

export default function SentinelPage() {
  const checks = deviceChecks()
  const ready = checks.every((c) => c.ok)

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <PageHeader
        eyebrow="Sentinel"
        title="Be the eyes of the street"
        description="Riders already on the road share a street photo every few seconds. An AI reads the lighting, activity and open places, and the map updates for everyone."
        aside={<Badge tone={ready ? 'ok' : 'warn'}>{ready ? 'This device is ready' : 'Device needs attention'}</Badge>}
      />

      <div className="grid gap-6 md:grid-cols-2">
        <Panel title="This device">
          <ul className="space-y-3">
            {checks.map((c) => (
              <li key={c.label} className="flex items-start gap-3">
                <span
                  className={`mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full ${c.ok ? 'bg-safe/15 text-safe' : 'bg-danger/15 text-danger'}`}
                >
                  {c.ok ? <CheckIcon size={14} /> : <XIcon size={14} />}
                </span>
                <div>
                  <p className="text-sm font-medium text-ink-100">{c.label}</p>
                  {!c.ok && <p className="text-xs text-ink-400">{c.help}</p>}
                </div>
              </li>
            ))}
          </ul>
          <button
            disabled
            className="mt-6 flex w-full items-center justify-center gap-2 rounded-xl bg-beacon-400 px-4 py-3 font-semibold text-ink-950 disabled:cursor-not-allowed disabled:opacity-40"
          >
            <CameraIcon size={18} /> Start Sentinel Mode
          </button>
          <div className="mt-3">
            <InDevelopment>Photo capture is the next Sentinel build step</InDevelopment>
          </div>
        </Panel>

        <Panel title="Capture rules">
          <dl className="divide-y divide-ink-700">
            {RULES.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-4 py-2.5 text-sm">
                <dt className="text-ink-400">{k}</dt>
                <dd className="text-right text-ink-100">{v}</dd>
              </div>
            ))}
          </dl>
          <p className="mt-4 text-xs text-ink-400">
            Nothing is captured unless you switch Sentinel Mode on. Point the camera at the road, not at people or homes.
          </p>
        </Panel>
      </div>
    </div>
  )
}
