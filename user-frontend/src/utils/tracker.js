/**
 * tracker.js — Silent behaviour tracking.
 * Sends events to /api/track when user is logged in.
 * Session ID comes from login response.
 */
import { trackEvent } from './api'

let _sessionId = null

export const tracker = {
  setSession(sid) { _sessionId = sid },

  async fire(eventType, courseSlug = null, timeSpentSec = 0) {
    if (!_sessionId) return
    try {
      await trackEvent({ session_id: _sessionId, course_slug: courseSlug, event_type: eventType, time_spent_sec: timeSpentSec })
    } catch {}
  },

  pageView   (slug, sec)  { this.fire('page_view',       slug, sec) },
  video      (slug)       { this.fire('video_play',       slug) },
  brochure   (slug)       { this.fire('brochure_dl',      slug) },
  chat       ()           { this.fire('chat') },
  pricing    (slug)       { this.fire('pricing_view',     slug) },
  testimonial(slug)       { this.fire('testimonial_view', slug) },
  webinar    (slug)       { this.fire('webinar_view',     slug) },
  cartAdd    (slug)       { this.fire('cart_add',         slug) },
  wishlistAdd(slug)       { this.fire('wishlist_add',     slug) },
}
