/**
 * tracker.js — Silent behaviour tracking (feeds the lead-scoring model).
 *
 * What it measures, and how it maps to the model's features:
 *   visit        a new session starts on first activity, and again after
 *                30 min of inactivity           -> TotalVisits
 *   page time    seconds on every page, sent when you leave it (or hide the tab)
 *                                               -> TotalTimeOnWebsite, PageViewsPerVisit
 *   device       from the browser's user agent  -> DeviceType
 *   source       utm_source / referrer of the landing page -> LeadSource
 *   intent       video, brochure, chat, pricing / testimonial *dwell* (4 s in view),
 *                webinar seat, cart, wishlist, checkout
 *   presence     a "still here" ping every 30 s while the page is really in use, so
 *                the CRM's "visit ended" follow-up waits until the learner has left
 *
 * Before: the session id from login was reused forever (TotalVisits stuck at 1),
 * device was always "Desktop", source always "Direct Traffic", and pricing /
 * testimonial / webinar fired as soon as the section scrolled past.
 */
import { startSession, trackEvent, pingSession } from './api'

const IDLE_MS = 30 * 60 * 1000
const PING_MS = 30 * 1000          // "still here" while the learner is using the page
const PRESENT_MS = 60 * 1000       // ... i.e. clicked, typed, scrolled or moved the mouse in the last minute
const LS_SID = 'xe_sid'
const LS_LAST = 'xe_last_active'
const SS_SOURCE = 'xe_source'

function detectDevice() {
  const ua = navigator.userAgent || ''
  if (/iPad|Tablet|PlayBook|Silk/i.test(ua) || (/Android/i.test(ua) && !/Mobile/i.test(ua))) return 'Tablet'
  if (/Mobi|Android|iPhone|iPod/i.test(ua)) return 'Mobile'
  return 'Desktop'
}

const UTM_MAP = [
  [/google|adwords|cpc|ppc/, 'Google'], [/facebook|instagram|meta|twitter|x\.com/, 'Social Media'],
  [/linkedin/, 'LinkedIn'], [/youtube/, 'YouTube'], [/email|newsletter|mail/, 'Email Campaign'],
  [/webinar/, 'Webinar'], [/referral|reference|friend/, 'Reference'], [/chat|olark/, 'Olark Chat'],
]
const REFERRER_MAP = [
  [/google\.|bing\.|duckduckgo\.|yahoo\./, 'Organic Search'], [/linkedin\./, 'LinkedIn'],
  [/youtube\.|youtu\.be/, 'YouTube'], [/facebook\.|instagram\.|t\.co|twitter\.|x\.com/, 'Social Media'],
  [/mail\.|outlook\./, 'Email Campaign'],
]

/** Called once when the app loads: remember how this visitor arrived. */
export function captureSource() {
  try {
    if (sessionStorage.getItem(SS_SOURCE)) return
    const params = new URLSearchParams(window.location.search)
    const utm = (params.get('utm_source') || '').toLowerCase()
    let source = 'Direct Traffic'
    if (params.get('ref')) source = 'Email Campaign'            // arrived from the button in one of our emails
    else if (utm) source = (UTM_MAP.find(([re]) => re.test(utm)) || [null, 'Reference'])[1]
    else if (document.referrer && !document.referrer.startsWith(window.location.origin)) {
      const hit = REFERRER_MAP.find(([re]) => re.test(document.referrer))
      if (hit) source = hit[1]
    }
    sessionStorage.setItem(SS_SOURCE, source)
  } catch { /* storage blocked: fall back to Direct Traffic */ }
}

function getSource() {
  try { return sessionStorage.getItem(SS_SOURCE) || 'Direct Traffic' } catch { return 'Direct Traffic' }
}

let _sessionId = null
let _starting = null
let _page = null        // { slug, started }

function loggedIn() { return !!localStorage.getItem('xe_token') }

async function ensureSession() {
  if (!loggedIn()) return null
  const last = Number(localStorage.getItem(LS_LAST) || 0)
  const stored = Number(localStorage.getItem(LS_SID) || 0) || null
  if (!_sessionId && stored && Date.now() - last < IDLE_MS) _sessionId = stored
  if (_sessionId && Date.now() - last < IDLE_MS) return _sessionId
  if (!_starting) {
    _starting = startSession({ device_type: detectDevice(), lead_source: getSource() })
      .then(r => {
        _sessionId = r.data.session_id
        localStorage.setItem(LS_SID, _sessionId)
        return _sessionId
      })
      .catch(() => null)
      .finally(() => { _starting = null })
  }
  return _starting
}

async function fire(eventType, courseSlug = null, timeSpentSec = 0) {
  if (!loggedIn()) return
  const sid = await ensureSession()
  if (!sid) return
  localStorage.setItem(LS_LAST, String(Date.now()))
  try {
    await trackEvent({ session_id: sid, course_slug: courseSlug, event_type: eventType, time_spent_sec: timeSpentSec })
  } catch { /* tracking must never break the page */ }
}

/** Send the time spent on the current page even while the tab is closing. */
function flushPage(useBeacon = false) {
  if (!_page) return
  const sec = Math.min(Math.round((Date.now() - _page.started) / 1000), 1800)
  const slug = _page.slug
  _page = null
  if (sec < 1 || !loggedIn()) return
  if (useBeacon && _sessionId) {
    try {
      fetch('/api/track', {
        method: 'POST', keepalive: true,
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${localStorage.getItem('xe_token')}` },
        body: JSON.stringify({ session_id: _sessionId, course_slug: slug, event_type: 'page_view', time_spent_sec: sec }),
      })
      localStorage.setItem(LS_LAST, String(Date.now()))
    } catch { /* ignore */ }
    return
  }
  fire('page_view', slug, sec)
}

// "Still here": while the learner is really using the page (tab visible, some input in the last minute),
// tell the server every 30 s. Nothing is recorded as an event; only the visit's last-active time moves,
// so the CRM does not take a long read for a visit that has ended (it follows up after the learner leaves).
let _lastInput = Date.now()
async function stillHere() {
  if (!loggedIn() || document.visibilityState !== 'visible') return
  if (Date.now() - _lastInput > PRESENT_MS) return
  const sid = _sessionId || await ensureSession()      // after a page reload the visit is picked up again
  if (!sid) return
  localStorage.setItem(LS_LAST, String(Date.now()))
  pingSession({ session_id: sid }).catch(() => { /* never breaks the page */ })
}
if (typeof window !== 'undefined') {
  ['mousemove', 'keydown', 'scroll', 'click', 'touchstart'].forEach(ev =>
    window.addEventListener(ev, () => { _lastInput = Date.now() }, { passive: true }))
  setTimeout(stillHere, 5000)
  setInterval(stillHere, PING_MS)
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') {
      const slug = _page?.slug ?? null
      flushPage(true)
      _page = { slug, started: null }            // paused until the tab is visible again
    } else if (_page && _page.started === null) {
      _page.started = Date.now()
    }
  })
}

/**
 * Fires `onDwell` once the element has been at least `threshold` visible for `ms`
 * continuously — "actually looked at", not "scrolled past". Returns a cleanup fn.
 */
export function observeDwell(el, onDwell, { ms = 4000, threshold = 0.4 } = {}) {
  if (!el) return () => {}
  let timer = null
  const obs = new IntersectionObserver(([e]) => {
    if (e.isIntersecting) {
      if (!timer) timer = setTimeout(() => { onDwell(); obs.disconnect() }, ms)
    } else if (timer) { clearTimeout(timer); timer = null }
  }, { threshold })
  obs.observe(el)
  return () => { if (timer) clearTimeout(timer); obs.disconnect() }
}

export const tracker = {
  /** Start a fresh visit (call right after login / signup). */
  newSession() {
    _sessionId = null
    localStorage.removeItem(LS_SID)
    localStorage.removeItem(LS_LAST)
    return ensureSession()
  },
  /** Kept for old callers; the tracker now manages sessions itself. */
  setSession() {},

  /** Route changed: close the previous page's timer and start a new one. */
  pageChange(slug = null) {
    if (_page && _page.started) flushPage(false)
    _page = { slug, started: Date.now() }
  },

  video      (slug) { fire('video_play',       slug) },
  brochure   (slug) { fire('brochure_dl',      slug) },
  chat       ()     { fire('chat') },
  pricing    (slug) { fire('pricing_view',     slug) },
  testimonial(slug) { fire('testimonial_view', slug) },
  webinar    (slug) { fire('webinar_register', slug) },
  cartAdd    (slug) { fire('cart_add',         slug) },
  wishlistAdd(slug) { fire('wishlist_add',     slug) },
  checkoutStart(slug) { fire('checkout_start', slug) },
}
