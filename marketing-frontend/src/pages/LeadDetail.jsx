import { useEffect, useState } from 'react'
import { useParams, Link }     from 'react-router-dom'
import { getLead, sendEmail, aiImprove, queueSms, generateCoupon } from '../utils/api'

export default function LeadDetail() {
  const { id }      = useParams()
  const [lead,      setLead]      = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [subject,   setSubject]   = useState('')
  const [body,      setBody]      = useState('')
  const [smsMsg,    setSmsMsg]    = useState('')
  const [improving, setImproving] = useState(false)
  const [sending,   setSending]   = useState(false)
  const [smsBusy,   setSmsBusy]   = useState(false)
  const [couponBusy,setCouponBusy]= useState(false)
  const [msg,       setMsg]       = useState('')
  const [smsResult, setSmsResult] = useState('')
  const [couponResult,setCouponResult] = useState('')
  const [tab,       setTab]       = useState('email') // email | sms | behaviour | coupon

  useEffect(() => {
    getLead(id)
      .then(r => {
        setLead(r.data)
        setSubject(r.data.email_subject || '')
        setBody(r.data.email_body || '')
        setSmsMsg(r.data.whatsapp_message || '')
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [id])

  async function handleImprove() {
    setImproving(true)
    try {
      const r = await aiImprove({ draft: body, tier: lead.recommended_action, course: lead.course_type, occupation: lead.current_occupation || '', name: lead.name || '' })
      setSubject(r.data.improved_subject)
      setBody(r.data.improved_body)
      setSmsMsg(r.data.whatsapp_message)
      setMsg(' AI has improved the email content. Review before sending.')
    } catch { setMsg(' AI improve failed') }
    finally { setImproving(false) }
  }

  async function handleSend() {
    setSending(true); setMsg('')
    try {
      const r = await sendEmail({ lead_id: Number(id), subject, body })
      setMsg(r.data.success ? ' ' + r.data.message : ' ' + r.data.message)
      if (r.data.success) setLead(l => ({...l, email_sent:1}))
    } catch(e) { setMsg(' ' + (e.response?.data?.detail || 'Error')) }
    finally { setSending(false) }
  }

  async function handleSms() {
    setSmsBusy(true)
    try {
      await queueSms({ user_id: lead.user_id, phone: lead.phone || 'N/A', message: smsMsg })
      setSmsResult(' SMS queued (mock mode — configure Fast2SMS API to send real messages)')
    } catch { setSmsResult(' Failed to queue SMS') }
    finally { setSmsBusy(false) }
  }

  async function handleCoupon() {
    setCouponBusy(true)
    const discounts = { 'Target Immediately':25, 'Nurture via Email/WhatsApp':15, 'Marketing Campaign':10 }
    const disc = discounts[lead?.recommended_action] || 10
    try {
      const r = await generateCoupon({ user_id: lead.user_id, tier: lead.recommended_action, discount_pct: disc })
      setCouponResult(` Coupon ${r.data.coupon_code} (${r.data.discount_pct}% off) assigned to user.`)
    } catch(e) { setCouponResult(' ' + (e.response?.data?.detail || 'Error')) }
    finally { setCouponBusy(false) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin"/></div>
  if (!lead)   return <p className="text-slate-500 text-center mt-20">Lead not found.</p>

  const SC = s => s>=80?'text-red-400':s>=60?'text-orange-400':s>=40?'text-yellow-400':'text-slate-400'

  return (
    <div>
      <div className="flex items-center gap-4 mb-6">
        <Link to="/leads" className="text-slate-500 hover:text-white text-sm">← Back to Leads</Link>
        <h1 className="font-display text-2xl font-bold text-white">{lead.name}</h1>
        <span className={`font-display text-3xl font-extrabold ${SC(lead.lead_score)}`}>{lead.lead_score}<span className="text-slate-600 text-base font-normal">/100</span></span>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        {/* Profile card */}
        <div className="card p-6 space-y-3 text-sm h-fit">
          <h3 className="font-display font-semibold text-white mb-2">Profile</h3>
          {[
            ['Email',      lead.email],
            ['Phone',      lead.phone || '—'],
            ['Occupation', lead.current_occupation],
            ['Specializ.', lead.specialization],
            ['City',       lead.city],
            ['Age Bracket',lead.age_bracket || '—'],
            ['Course',     lead.course_type],
            ['Persona',    lead.persona],
            ['Segment',    lead.customer_segment],
            ['Trigger',    lead.trigger_reason],
            ['Conv. Prob.',`${((lead.conversion_probability||0)*100).toFixed(1)}%`],
            ['WhatsApp',   lead.whatsapp_opt_in ? 'Yes Opted In' : '—'],
            ['Coupon',     lead.coupon_code || '—'],
          ].map(([k,v]) => v && (
            <div key={k} className="flex gap-2">
              <span className="text-slate-500 w-24 flex-shrink-0">{k}</span>
              <span className="text-slate-200 break-all font-medium">{v}</span>
            </div>
          ))}
          {lead.call_script && (
            <div className="mt-4 pt-4 border-t border-white/10">
              <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide mb-2">Phone: Call Script</p>
              <p className="text-slate-300 text-xs leading-relaxed italic">{lead.call_script}</p>
            </div>
          )}
        </div>

        {/* Action panel */}
        <div className="lg:col-span-2 space-y-4">
          {/* Tab selector */}
          <div className="flex gap-2">
            {[['email',' Email'],['sms',' SMS/WhatsApp'],['behaviour',' Behaviour'],['coupon',' Coupon']].map(([key,label]) => (
              <button key={key} onClick={() => setTab(key)}
                className={`px-4 py-2 rounded-xl text-sm font-medium transition-all
                  ${tab===key?'bg-ember text-white':'bg-white/5 border border-white/10 text-slate-400 hover:border-white/30'}`}>
                {label}
              </button>
            ))}
          </div>

          {/* EMAIL TAB */}
          {tab==='email' && (
            <div className="card p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-display font-semibold text-white">Email Editor</h3>
                <button onClick={handleImprove} disabled={improving}
                  className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-xl text-sm font-medium transition-all disabled:opacity-60">
                  {improving ? ' Improving…' : ' Improve with AI'}
                </button>
              </div>
              <div>
                <label className="lbl">Subject Line</label>
                <input value={subject} onChange={e=>setSubject(e.target.value)} className="inp"/>
              </div>
              <div>
                <label className="lbl">Email Body</label>
                <textarea value={body} onChange={e=>setBody(e.target.value)} rows={12} className="inp font-mono text-xs leading-relaxed"/>
              </div>
              {msg && <p className="text-sm">{msg}</p>}
              {lead.email_sent
                ? <p className="text-green-400 text-sm font-semibold text-center"> Email already sent · {lead.email_sent_at}</p>
                : <button onClick={handleSend} disabled={sending}
                    className="w-full btn disabled:opacity-60">
                    {sending ? ' Sending…' : ' Send Email to Lead'}
                  </button>
              }
            </div>
          )}

          {/* SMS TAB */}
          {tab==='sms' && (
            <div className="card p-6 space-y-4">
              <h3 className="font-display font-semibold text-white">WhatsApp / SMS Composer</h3>
              <div>
                <label className="lbl">Message (max 160 chars for SMS)</label>
                <textarea value={smsMsg} onChange={e=>setSmsMsg(e.target.value)} rows={5} maxLength={500} className="inp font-mono text-sm"/>
                <p className="text-slate-600 text-xs mt-1">{smsMsg.length} characters</p>
              </div>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-xs text-slate-400">
                <p className="font-semibold text-slate-300 mb-1"> Send to: {lead.phone || 'No phone on file'}</p>
                <p>WhatsApp opt-in: {lead.whatsapp_opt_in ? 'Yes Yes' : 'No No'}</p>
              </div>
              {smsResult && <p className="text-sm">{smsResult}</p>}
              <button onClick={handleSms} disabled={smsBusy}
                className="w-full btn disabled:opacity-60">
                {smsBusy ? ' Queuing…' : ' Queue SMS (Mock)'}
              </button>
              <p className="text-slate-600 text-xs text-center">To send real SMS, configure Fast2SMS or MSG91 API in marketing-backend/.env</p>
            </div>
          )}

          {/* BEHAVIOUR TAB */}
          {tab==='behaviour' && (
            <div className="card p-6">
              <h3 className="font-display font-semibold text-white mb-5">Behaviour Timeline</h3>
              <div className="grid grid-cols-3 gap-3 mb-6">
                {[
                  ['Total Visits',   lead.total_visits],
                  ['Time on Site',   `${lead.total_time_on_website}s`],
                  ['Pages/Visit',    lead.page_views_per_visit],
                  ['Sessions',       lead.sessions_count],
                  ['Emails Opened',  lead.email_opened_count],
                  ['Lead Source',    lead.lead_source || '—'],
                  ['Video',          lead.video_watched    ?'Yes Yes':'—'],
                  ['Brochure',       lead.brochure_downloaded?'Yes Yes':'—'],
                  ['Chat',           lead.chat_initiated   ?'Yes Yes':'—'],
                  ['Pricing Page',   lead.pricing_page_visited?'Yes Yes':'—'],
                  ['Testimonial',    lead.testimonial_visited?'Yes Yes':'—'],
                  ['Webinar',        lead.webinar_attended ?'Yes Yes':'—'],
                ].map(([k,v]) => (
                  <div key={k} className="bg-white/5 rounded-xl px-3 py-2.5">
                    <p className="text-slate-500 text-xs">{k}</p>
                    <p className="text-white font-semibold text-sm">{v}</p>
                  </div>
                ))}
              </div>
              {lead.behaviour_events?.length > 0 && (
                <>
                  <h4 className="text-slate-400 text-xs uppercase tracking-wide mb-3 font-semibold">Recent Events</h4>
                  <div className="space-y-2 max-h-48 overflow-y-auto">
                    {lead.behaviour_events.map(e => (
                      <div key={e.id} className="flex items-center gap-3 text-xs text-slate-400">
                        <span className="w-20 flex-shrink-0 text-slate-600">{new Date(e.created_at).toLocaleTimeString('en-IN',{hour:'2-digit',minute:'2-digit'})}</span>
                        <span className="bg-white/5 px-2 py-0.5 rounded-full">{e.event_type}</span>
                        {e.course_slug && <span className="text-slate-600">{e.course_slug}</span>}
                        {e.time_spent_sec > 0 && <span className="text-slate-600">{e.time_spent_sec}s</span>}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {/* COUPON TAB */}
          {tab==='coupon' && (
            <div className="card p-6 space-y-4">
              <h3 className="font-display font-semibold text-white">Coupon Generator</h3>
              <div className="bg-white/5 border border-white/10 rounded-xl p-4 text-sm space-y-2">
                <p className="text-slate-300">Tier: <span className="font-semibold text-white">{lead.recommended_action}</span></p>
                {lead.recommended_action==='Target Immediately'    && <p className="text-slate-400">→ Will generate <span className="font-mono text-ember">VIP_URGENT_25</span> (25% off, 72hr expiry)</p>}
                {lead.recommended_action==='Nurture via Email/WhatsApp' && <p className="text-slate-400">→ Will generate <span className="font-mono text-orange-400">FUTURE_READY_15</span> (15% off, 72hr expiry)</p>}
                {lead.recommended_action==='Marketing Campaign'    && <p className="text-slate-400">→ Will generate <span className="font-mono text-yellow-400">EARLY_BIRD_10</span> (10% off, 72hr expiry)</p>}
                {lead.recommended_action==='Low Priority'          && <p className="text-slate-500 italic">Low Priority users do not receive coupons. Nurture them first.</p>}
              </div>
              {lead.recommended_action !== 'Low Priority' && (
                <>
                  <p className="text-slate-500 text-xs">The coupon will be assigned to this user's account. It will appear when they log in and must be entered manually at checkout. Send it via email to notify them.</p>
                  {couponResult && <p className="text-sm">{couponResult}</p>}
                  <button onClick={handleCoupon} disabled={couponBusy} className="w-full btn disabled:opacity-60">
                    {couponBusy ? ' Generating…' : ' Generate & Assign Coupon'}
                  </button>
                </>
              )}
              {lead.coupons?.length > 0 && (
                <div className="mt-4 pt-4 border-t border-white/10">
                  <p className="text-slate-500 text-xs uppercase tracking-wide font-semibold mb-3">Previously Issued</p>
                  {lead.coupons.map(c => (
                    <div key={c.id} className="flex items-center justify-between text-xs py-1.5">
                      <span className="font-mono text-ember">{c.coupon_code}</span>
                      <span className="text-slate-400">{c.discount_pct}% off</span>
                      <span className={c.used?'text-slate-600':'text-green-400'}>{c.used?'Used':'Active'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
