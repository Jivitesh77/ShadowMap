// Read text aloud with the browser's built-in voices (no paid service). Text is always shown on screen too.
import type { Lang } from '../api'

export function speechSupported(): boolean {
  return typeof window !== 'undefined' && 'speechSynthesis' in window
}

function pickVoice(lang: Lang): SpeechSynthesisVoice | null {
  const voices = window.speechSynthesis.getVoices()
  const wanted = lang === 'hi' ? ['hi-IN', 'hi'] : ['en-IN', 'en-GB', 'en-US', 'en']
  for (const w of wanted) {
    const v = voices.find((x) => x.lang.toLowerCase().startsWith(w.toLowerCase()))
    if (v) return v
  }
  return null
}

/** Speaks the text. Resolves false if this device has no voice for the language. */
export function speak(text: string, lang: Lang, onEnd?: () => void): boolean {
  if (!speechSupported()) return false
  window.speechSynthesis.cancel()
  const voice = pickVoice(lang)
  if (!voice && lang === 'hi') return false
  const u = new SpeechSynthesisUtterance(text)
  u.lang = lang === 'hi' ? 'hi-IN' : 'en-IN'
  if (voice) u.voice = voice
  u.rate = 0.95
  u.onend = () => onEnd?.()
  u.onerror = () => onEnd?.()
  window.speechSynthesis.speak(u)
  return true
}

export function stopSpeaking() {
  if (speechSupported()) window.speechSynthesis.cancel()
}
