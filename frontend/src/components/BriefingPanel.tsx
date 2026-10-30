// Route briefing in English or Hindi, read aloud with the browser's voice (blueprint §8).
import { useEffect, useState } from 'react'
import { api, type Briefing, type Lang, type LatLon } from '../api'
import { speak, speechSupported, stopSpeaking } from '../lib/speech'
import { ErrorState, Skeleton } from './States'

export function BriefingPanel({ start, end, at }: { start: LatLon; end: LatLon; at?: string }) {
  const [lang, setLang] = useState<Lang>('en')
  const [data, setData] = useState<Briefing | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [voiceNote, setVoiceNote] = useState<string | null>(null)

  // A new route or language makes the old briefing stale.
  useEffect(() => {
    setData(null)
    setError(null)
    stopSpeaking()
    setSpeaking(false)
  }, [start, end, at, lang])
  useEffect(() => () => stopSpeaking(), [])

  const load = async () => {
    setLoading(true)
    setError(null)
    setVoiceNote(null)
    try {
      const b = await api.briefing(start, end, lang, at)
      setData(b)
      read(b)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  const read = (b: Briefing) => {
    if (!speechSupported()) return setVoiceNote('This browser cannot read aloud. The briefing is shown above.')
    const ok = speak(b.text, b.lang, () => setSpeaking(false))
    if (!ok) setVoiceNote(b.lang === 'hi' ? 'No Hindi voice on this device. Read the text above, or switch to English.' : 'Could not read aloud.')
    setSpeaking(ok)
  }

  return (
    <section className="space-y-3 rounded-xl border border-ink-700 bg-ink-900/60 p-3" aria-labelledby="briefing-h">
      <div className="flex items-center justify-between gap-2">
        <h3 id="briefing-h" className="text-xs font-semibold uppercase tracking-wider text-ink-400">Route briefing</h3>
        <div className="inline-flex rounded-lg bg-ink-800 p-0.5 text-xs" role="group" aria-label="Briefing language">
          {(['en', 'hi'] as const).map((l) => (
            <button key={l} onClick={() => setLang(l)} aria-pressed={lang === l}
              className={`rounded-md px-2.5 py-1 ${lang === l ? 'bg-ink-100 text-ink-950' : 'text-ink-300'}`}>
              {l === 'en' ? 'English' : 'हिन्दी'}
            </button>
          ))}
        </div>
      </div>
      {!data && !loading && (
        <button onClick={load} className="min-h-11 w-full rounded-lg bg-beacon-400 px-3 py-2 text-sm font-semibold text-ink-950">
          Hear the briefing
        </button>
      )}
      {loading && <Skeleton className="h-20 w-full" />}
      {error && <ErrorState title="No briefing" message={error} onRetry={load} />}
      {data && (
        <>
          <p lang={data.lang} className="text-sm leading-relaxed text-ink-100">{data.text}</p>
          <div className="flex flex-wrap items-center gap-2">
            {speaking ? (
              <button onClick={() => { stopSpeaking(); setSpeaking(false) }} className="min-h-10 rounded-lg border border-ink-600 px-3 text-sm">Stop reading</button>
            ) : (
              <button onClick={() => read(data)} className="min-h-10 rounded-lg border border-ink-600 px-3 text-sm">Read aloud</button>
            )}
            <span className={`rounded-md px-2 py-0.5 text-xs ${data.source === 'ai' ? 'bg-ink-700 text-ink-100' : 'border border-ink-600 text-ink-300'}`}>
              {data.source === 'ai' ? `Written by AI (${data.model}) from ShadowMap data, fact-checked` : 'Summary from ShadowMap data (not AI)'}
            </span>
          </div>
          {data.note && <p className="text-xs text-ink-400">{data.note}</p>}
          {voiceNote && <p className="text-xs text-caution">{voiceNote}</p>}
        </>
      )}
    </section>
  )
}
