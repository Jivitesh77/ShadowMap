// Emergency help bar during a walk (blueprint §9). In DEMO MODE every button rings the team's demo number, never
// 112 / 181 / 100 / police. Each call also tells the trusted contacts "X is calling …".
import { useEffect, useRef, useState } from 'react'
import type { WalkConfig } from '../api'

type Target = '112' | '181' | 'police' | 'contact' | 'fake'

function FakeCall({ onClose }: { onClose: () => void }) {
  const [answered, setAnswered] = useState(false)
  const [secs, setSecs] = useState(0)
  useEffect(() => {
    // ring: vibrate and a simple tone (WebAudio), no audio files needed
    let ctx: AudioContext | null = null
    let timer: number | undefined
    if (!answered) {
      navigator.vibrate?.([600, 400, 600, 400, 600, 400, 600])
      try {
        ctx = new AudioContext()
        const ring = () => {
          if (!ctx) return
          const o = ctx.createOscillator()
          const g = ctx.createGain()
          o.frequency.value = 880
          g.gain.value = 0.08
          o.connect(g).connect(ctx.destination)
          o.start()
          o.stop(ctx.currentTime + 0.8)
        }
        ring()
        timer = window.setInterval(ring, 1600)
      } catch {
        /* no audio: vibration and screen only */
      }
    } else {
      timer = window.setInterval(() => setSecs((s) => s + 1), 1000)
    }
    return () => {
      clearInterval(timer)
      navigator.vibrate?.(0)
      ctx?.close().catch(() => {})
    }
  }, [answered])
  return (
    <div className="fixed inset-0 z-[3000] flex flex-col items-center justify-between bg-gradient-to-b from-ink-800 to-ink-950 p-10 text-center">
      <div className="mt-16">
        <p className="text-sm text-ink-300">{answered ? `${Math.floor(secs / 60)}:${String(secs % 60).padStart(2, '0')}` : 'Incoming call…'}</p>
        <p className="mt-2 text-3xl font-semibold">Maa</p>
        <p className="mt-1 text-ink-400">mobile</p>
      </div>
      <div className="mb-12 flex gap-16">
        <button onClick={onClose} aria-label="End call" className="grid h-16 w-16 place-items-center rounded-full bg-danger text-white">✕</button>
        {!answered && (
          <button onClick={() => setAnswered(true)} aria-label="Answer" className="grid h-16 w-16 place-items-center rounded-full bg-safe text-white">✓</button>
        )}
      </div>
    </div>
  )
}

export function HelpBar({
  config,
  policeStation,
  contactPhone,
  onCalling,
}: {
  config: WalkConfig
  policeStation: { name: string | null; phone: string | null; distance_m: number } | null
  contactPhone: string | null
  onCalling: (t: Target) => void
}) {
  const [fake, setFake] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [holding, setHolding] = useState(false)
  const holdTimer = useRef<number | null>(null)

  const realNumber = (t: Target) =>
    t === '112' ? config.helplines.emergency
      : t === '181' ? config.helplines.women
        : t === 'police' ? policeStation?.phone || config.helplines.police
          : contactPhone

  const call = (t: Target) => {
    onCalling(t)
    const number = config.demo_mode ? config.demo_call_number : realNumber(t)
    if (!number) {
      setMsg(config.demo_mode
        ? 'Demo mode: no team phone number is set (DEMO_CALL_NUMBER in backend/.env), so nothing was dialled. Contacts were told.'
        : 'No number available for this button.')
      return
    }
    setMsg(config.demo_mode ? `Demo mode: calling the team phone instead of ${t === 'contact' ? 'your contact' : realNumber(t)}.` : null)
    window.location.href = `tel:${number.replace(/\s/g, '')}`
  }

  // 112 needs a 1-second press so it cannot be dialled by accident (blueprint §9)
  const startHold = () => {
    setHolding(true)
    holdTimer.current = window.setTimeout(() => {
      setHolding(false)
      call('112')
    }, 1000)
  }
  const endHold = () => {
    setHolding(false)
    if (holdTimer.current) clearTimeout(holdTimer.current)
  }

  const btn = 'flex min-h-14 flex-1 flex-col items-center justify-center rounded-xl px-1 text-[11px] font-semibold leading-tight'
  return (
    <>
      {fake && <FakeCall onClose={() => setFake(false)} />}
      <div className="space-y-1">
        {msg && <p className="rounded-lg bg-ink-800 px-3 py-1.5 text-xs text-ink-200" role="status">{msg}</p>}
        <div className="flex gap-1.5" role="group" aria-label="Help calls">
          <button onPointerDown={startHold} onPointerUp={endHold} onPointerLeave={endHold} onContextMenu={(e) => e.preventDefault()}
            className={`${btn} ${holding ? 'bg-white text-danger' : 'bg-danger text-white'}`}>
            <span className="text-base">112</span>hold 1 s
          </button>
          <button onClick={() => call('181')} className={`${btn} bg-ink-700 text-ink-100`}><span className="text-base">181</span>Women help</button>
          <button onClick={() => call('police')} className={`${btn} bg-ink-700 text-ink-100`}>
            <span className="text-base">Police</span>{policeStation ? `${(policeStation.distance_m / 1000).toFixed(1)} km` : 'nearest'}
          </button>
          <button onClick={() => call('contact')} className={`${btn} bg-ink-700 text-ink-100`}><span className="text-base">Contact</span>call</button>
          <button onClick={() => { onCalling('fake'); setFake(true) }} className={`${btn} bg-ink-800 text-ink-300`}><span className="text-base">Fake</span>call</button>
        </div>
        {config.demo_mode && <p className="text-center text-[10px] text-beacon-300">Demo mode: calls ring a team phone, never real emergency numbers.</p>}
      </div>
    </>
  )
}
