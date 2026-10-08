// Plain-words labels used across the dashboard (one place, so every page says the same thing).

// Lifecycle stages: the standard CRM names (HubSpot/Salesforce) with plain words first.
// MQL = marketing-qualified lead (showed interest: pricing, wishlist, chat) — marketing keeps nurturing.
// SQL = sales-qualified lead (ready to buy: enquiry, cart, checkout, asked for a call) — sales should contact now.
export const STAGE_LABEL = {
  Lead: 'New lead', Engaged: 'Engaged', MQL: 'Interested (MQL)', SQL: 'Ready to buy (SQL)', Customer: 'Customer',
}
export const STAGE_HELP = {
  Lead: 'Signed up, nothing else yet',
  Engaged: 'Watched a video, read the brochure or testimonials, joined a webinar, or came back',
  MQL: 'Marketing-qualified: looked at pricing, wishlisted a course or used the chat',
  SQL: 'Sales-qualified: sent an enquiry, added to cart or started checkout',
  Customer: 'Bought a course',
}
export const stageLabel = s => STAGE_LABEL[s] || s

export const TIER_SHORT = {
  'Target Immediately': 'Target Now', 'Nurture via Email/WhatsApp': 'Nurture', 'Marketing Campaign': 'Campaign',
  'Low Priority': 'Low Prio',
}

export const TRIGGER_LABEL = {
  session_end: 'Visit ended', cart_abandon: 'Cart left', checkout_abandon: 'Checkout left', wishlist: 'Wishlisted',
  enquiry: 'Enquiry', chat_callback: 'Asked for a call', signup: 'Signed up', manual: 'By hand', campaign: 'Campaign',
}
export const triggerLabel = t => TRIGGER_LABEL[t] || (t || '').replaceAll('_', ' ')

// why a score changed (lead_score_history.reason)
export const REASON_LABEL = {
  activity: 'website activity', email_click: 'clicked an email', purchase_conversion: 'bought a course',
  manual_rescore: 're-scored by hand (old version)', model_update: 'new model from the learning loop',
  time_away: 'time since the last visit', signup: 'signed up', session_end: 'visit ended', cart_abandon: 'cart left',
  checkout_abandon: 'checkout left', wishlist: 'wishlisted', enquiry: 'enquiry', manual: 'step taken by hand',
  decay: 'old “decay” rule (removed in v6.2)', chat_callback: 'asked for a call', lead_page: 'lead page',
}
export const reasonLabel = r => REASON_LABEL[r] || (r || '').replaceAll('_', ' ')

export const isSimulated = email => (email || '').toLowerCase().endsWith('@demo.xeducation.test')

export const ago = d => {
  if (!d) return '—'
  const m = (Date.now() - new Date(String(d).replace(' ', 'T')).getTime()) / 60000
  if (m < 1) return 'just now'
  if (m < 60) return `${Math.round(m)} min ago`
  if (m < 60 * 48) return `${Math.round(m / 60)} h ago`
  return `${Math.round(m / 1440)} days ago`
}
export const daysText = d => (d == null ? '—' : d < 1 ? 'today' : d < 2 ? '1 day ago' : `${Math.round(d)} days ago`)

export const ACTION_LABEL = {
  none: 'Do nothing', email_info: 'Information email', email_coupon_10: 'Email + 10% coupon',
  email_coupon_20: 'Email + 20% coupon', call: 'Advisor call', whatsapp: 'WhatsApp message',
}
export const actionLabel = a => ACTION_LABEL[a] || (a || '').replaceAll('_', ' ')
