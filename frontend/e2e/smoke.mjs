// ShadowMap browser smoke test — no extra packages: Node's built-in WebSocket drives the locally installed Chrome over
// the DevTools protocol. Run against a TEST copy of the app (never the real database):
//
//   SMOKE_BASE=http://localhost:5174 SMOKE_SENTINEL=<test code> SMOKE_OUT=/tmp/shadowmap-smoke node e2e/smoke.mjs
//
// Use the production build (`vite preview`): the dev server's React StrictMode deliberately sends first requests twice.
// It checks the main workflows, takes screenshots at 360 / 390 / 768 / 1440 px and reports horizontal overflow.
// It creates a simulated walk and a test report, so only use a disposable database.
import { spawn } from 'node:child_process'
import { mkdirSync, writeFileSync } from 'node:fs'

const BASE = process.env.SMOKE_BASE ?? 'http://localhost:5174'
const OUT = process.env.SMOKE_OUT ?? '/tmp/shadowmap-smoke'
const SENTINEL = process.env.SMOKE_SENTINEL ?? ''
const CHROME = process.env.SMOKE_CHROME ?? 'google-chrome-stable'
const PORT = 9400 + Math.floor(Math.random() * 400)
mkdirSync(OUT, { recursive: true })

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const results = []
const check = (name, ok, info = '') => results.push({ ok: !!ok, name, info })
let chrome, ws, seq = 0
const pending = new Map()
const requests = []
const problems = []

async function launch() {
  chrome = spawn(CHROME, ['--headless=new', '--disable-gpu', `--remote-debugging-port=${PORT}`, `--user-data-dir=${OUT}/profile`, 'about:blank'], { stdio: 'ignore' })
  for (let i = 0; i < 80; i++) {
    try {
      const page = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find((t) => t.type === 'page')
      if (page) { ws = new WebSocket(page.webSocketDebuggerUrl); break }
    } catch { /* not up yet */ }
    await sleep(250)
  }
  await new Promise((r) => ws.addEventListener('open', r))
  ws.addEventListener('message', (m) => {
    const d = JSON.parse(m.data)
    if (d.id && pending.has(d.id)) { const p = pending.get(d.id); pending.delete(d.id); d.error ? p.rej(new Error(d.error.message)) : p.res(d.result); return }
    if (d.method === 'Network.requestWillBeSent') requests.push({ method: d.params.request.method, url: d.params.request.url, body: d.params.request.postData ?? '' })
    if (d.method === 'Runtime.exceptionThrown') problems.push(d.params.exceptionDetails.exception?.description ?? d.params.exceptionDetails.text)
  })
  for (const m of ['Page.enable', 'Runtime.enable', 'Network.enable']) await send(m)
}
const send = (method, params = {}) => new Promise((res, rej) => { const id = ++seq; pending.set(id, { res, rej }); ws.send(JSON.stringify({ id, method, params })) })
const js = async (expr) => (await send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true })).result.value
const size = (width, height = 900) => send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 768 })
const go = async (path, wait = 3500) => { await send('Page.navigate', { url: BASE + path }); await sleep(wait) }
const shot = async (name) => { const r = await send('Page.captureScreenshot', { format: 'png' }); writeFileSync(`${OUT}/${name}.png`, Buffer.from(r.data, 'base64')) }
const text = () => js('document.body.innerText')
const overflow = () => js('document.documentElement.scrollWidth - window.innerWidth')
const clickText = (selector, t) => js(`(() => { const el = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.textContent.trim().startsWith(${JSON.stringify(t)})); if (!el) return false; el.click(); return true })()`)
const apiJson = (path, init) => js(`fetch(${JSON.stringify(path)}, ${JSON.stringify(init ?? {})}).then(r => r.json())`)

try {
  await launch()
  await size(1440)

  // 1. Walker, Delhi: one full map load, then only light score refreshes; busy categories hidden; data age shown
  requests.length = 0
  await go('/?city=delhi', 6000)
  const mapCalls = requests.filter((r) => r.url.includes('/api/map'))
  check('Delhi map: exactly one full map download', mapCalls.filter((r) => !r.url.includes('view=scores')).length === 1, mapCalls.map((r) => r.url.replace(BASE, '')).join(' '))
  const t1 = await text()
  check('Delhi: busy categories start hidden with an explanation', t1.includes('hidden to keep the map readable'))
  check('scores-updated time is shown', /scores updated/i.test(t1))
  await send('Runtime.evaluate', { expression: `document.querySelectorAll('.leaflet-marker-icon').length`, returnByValue: true }).then((r) => check('Delhi: pin count reduced (< 400)', r.result.value < 400, `${r.result.value} pins`))
  await shot('walker_delhi_1440')

  // 2. Changing the walk time refreshes scores only (no new full download)
  requests.length = 0
  await clickText('button', 'Travel time'); await sleep(300); await clickText('button', 'Tonight 11:30 pm'); await sleep(3000)
  const afterTime = requests.filter((r) => r.url.includes('/api/map'))
  check('changing the time loads only the light scores view', afterTime.length >= 1 && afterTime.every((r) => r.url.includes('view=scores')), afterTime.map((r) => r.url.replace(BASE, '')).join(' '))

  // 3. Route: planned once; "Compare routes" does not ask again; later re-plans are not counted
  await go('/?city=guwahati', 5000)
  requests.length = 0
  await clickText('button', 'Starting point'); await sleep(300); await clickText('[role=option]', 'IIIT Guwahati'); await sleep(300)
  await clickText('button', 'Destination'); await sleep(300)
  await js(`(() => { const o = [...document.querySelectorAll('[role=option]')].find(e => e.textContent.includes('Ranjeeta')) ?? [...document.querySelectorAll('[role=option]')][2]; o.click(); return 1 })()`); await sleep(3000)
  await clickText('button', 'Compare routes'); await sleep(2000)
  const routeCalls = requests.filter((r) => r.url.endsWith('/api/route'))
  check('one route request for one planned route (Compare does not repeat it)', routeCalls.length === 1, `${routeCalls.length} request(s)`)
  check('the first request is counted for the repair ranking', routeCalls[0] && JSON.parse(routeCalls[0].body).count === true)
  check('route cards shown', (await text()).includes('Suggested route'))
  requests.length = 0
  await clickText('button', 'Travel time'); await sleep(300); await clickText('button', 'Tonight 11:30 pm'); await sleep(3000)
  const replans = requests.filter((r) => r.url.endsWith('/api/route'))
  check('a re-plan after a time change is not counted again', replans.length >= 1 && replans.every((r) => JSON.parse(r.body).count === false))
  await shot('walker_route_1440')

  // 4. Keyboard: arrow keys move between the Walker tool tabs
  await js(`document.querySelector('[role=tab][aria-selected=true]').focus(); 1`)
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 })
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'ArrowRight', code: 'ArrowRight', windowsVirtualKeyCode: 39 })
  await sleep(300)
  check('arrow key selects and focuses the next tab', await js(`document.activeElement?.getAttribute('role') === 'tab' && document.activeElement.getAttribute('aria-selected') === 'true' && document.activeElement.textContent.trim() === 'Report'`))

  // 5. Contact page: honest arrival wording (simulated walk created through the API, test database only)
  const g = await apiJson('/api/cities')
  const centre = g.cities.find((c) => c.id === 'guwahati').center
  const walk = await apiJson('/api/walks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
    walker_name: 'Smoke Test', contacts: [{ name: 'Friend' }], pin: '1111', simulated: true,
    start: { lat: centre[0], lon: centre[1] }, end: { lat: centre[0] + 0.004, lon: centre[1] + 0.002 } }) })
  if (walk.walk_id) {
    await go(`/trip/${walk.walk_id}`, 3000)
    check('contact page shows the live walk', (await text()).includes('Smoke Test'))
    await shot('contact_live_1440')
    const dest = [centre[0] + 0.004, centre[1] + 0.002] // the destination the walk was started with
    await apiJson(`/api/walks/${walk.walk_id}/position`, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Walk-Token': walk.walker_token }, body: JSON.stringify({ lat: dest[0], lon: dest[1], accuracy_m: 5 }) })
    await go(`/trip/${walk.walk_id}`, 3000)
    const tc = await text()
    check('contact page after arrival: "phone reached the destination", never "reached safely"', tc.includes('phone reached the destination') && !/reached safely/i.test(tc))
    await shot('contact_arrived_1440')
  } else check('simulated walk created', false, JSON.stringify(walk).slice(0, 200))

  // 6. Sentinel: honest notices when AI / video tools are missing
  if (SENTINEL) {
    await go('/sentinel', 2500)
    await js(`(() => { const i = document.querySelector('input[aria-label="Sentinel access code"]'); const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(i, ${JSON.stringify(SENTINEL)}); i.dispatchEvent(new Event('input', { bubbles: true })); i.form.requestSubmit(); return 1 })()`)
    await sleep(3000)
    const status = await apiJson('/api/sentinel/status')
    const ts = await text()
    check('Sentinel opens with the test code', ts.includes('Sign out of Sentinel'))
    check('no-Gemini notice shown exactly when no key is set', status.ai_configured ? !ts.includes('AI analysis is not set up') : ts.includes('AI analysis is not set up'))
    check('video-unavailable notice shown exactly when FFmpeg is missing', status.video_available ? !ts.includes('Video mode unavailable') : ts.includes('Video mode unavailable'))
    await shot('sentinel_1440')
  }

  // 7. Layout at four widths: no sideways scrolling on any page
  const pages = [['walker', '/?city=delhi'], ['sentinel', '/sentinel'], ['police', '/police'], ['city', '/city'], ['contact', '/trip/not-a-real-trip']]
  for (const width of [360, 390, 768, 1440]) {
    await size(width, width < 768 ? 800 : 900)
    for (const [name, path] of pages) {
      await go(path, name === 'walker' ? 5000 : 2500)
      const extra = await overflow()
      check(`${name} at ${width}px: no sideways scrolling`, extra <= 1, extra > 1 ? `${extra}px too wide` : '')
      await shot(`${name}_${width}`)
    }
  }
  // the phone menu drawer opens and closes
  await size(390, 800)
  await go('/', 3500)
  await js(`document.querySelector('button[aria-label="Open menu"]').click(); 1`); await sleep(400)
  check('phone menu drawer opens', await js(`document.querySelector('button[aria-label="Open menu"]').getAttribute('aria-expanded') === 'true'`))
  await shot('drawer_390')
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await sleep(400)
  check('Escape closes the drawer', await js(`document.querySelector('button[aria-label="Open menu"]').getAttribute('aria-expanded') === 'false'`))
  check('no uncaught page errors', problems.length === 0, problems.slice(0, 3).join(' | '))
} catch (e) {
  check('smoke run finished without crashing', false, String(e))
} finally {
  chrome?.kill()
}
for (const r of results) console.log(`${r.ok ? 'PASS' : 'FAIL'}  ${r.name}${r.info ? `  [${r.info}]` : ''}`)
const failed = results.filter((r) => !r.ok).length
console.log(`${results.length - failed} of ${results.length} checks passed; screenshots in ${OUT}`)
process.exit(failed ? 1 : 0)
