import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getLead, sendEmail, aiImprove, whatsappLink, generateCoupon, getLeadExplain,
  getLeadAttribution, rescoreLead, closeCallback, getLeadPaths,
} from '../utils/api'

const fmt = d => d ? new Date(String(d).replace(' ', 'T')).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '—'
const yes = v => v ? 'Yes' : '—'
const p0 = x => (x == null ? '—' : `${(x * 100).toFixed(0)}%`)
const inr = x => (x == null ? '—' : `₹${Math.round(x).toLocaleString('en-IN')}`)
const REACT_COLOR = { advanced: '#22c55e', engaged: '#38BDF8', clicked: '#a78bfa', none: '#64748b' }

/* One team step → the learner's likely reactions → the best next step after each (from history + models). */
function PathTree({ lead, step }) {
  const rs = step.reactions || []
  const W = 820, nodeW = 178, rowH = 66, H = Math.max(rs.length, 1) * rowH + 24
  const col = [8, 214, 420, 632]
  const ys = rs.map((_, i) => 12 + i * rowH + rowH / 2 - 6)
  const mid = H / 2
  const box = (x, y, w, h, fill, stroke) => <rect x={x} y={y} width={w} height={h} rx="10" fill={fill} stroke={stroke} />
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="What-if path tree">
      {/* edges */}
      <path d={`M${col[0] + nodeW},${mid} L${col[1]},${mid}`} stroke="#f97316" strokeWidth="3" fill="none" />
      {rs.map((r, i) => (
        <g key={`e${i}`}>
          <path d={`M${col[1] + nodeW},${mid} C${col[1] + nodeW + 20},${mid} ${col[2] - 20},${ys[i]} ${col[2]},${ys[i]}`}
            stroke={REACT_COLOR[r.reaction] || '#64748b'} strokeOpacity="0.8" strokeWidth={Math.max(1.5, r.prob * 14)} fill="none" />
          <path d={`M${col[2] + nodeW},${ys[i]} L${col[3]},${ys[i]}`} stroke="#475569" strokeWidth="1.5" strokeDasharray="4 3" fill="none" />
        </g>
      ))}
      {/* now */}
      {box(col[0], mid - 30, nodeW, 60, 'rgba(255,255,255,0.05)', 'rgba(255,255,255,0.15)')}
      <text x={col[0] + 10} y={mid - 12} fill="#94a3b8" fontSize="10">NOW · {lead.stage}</text>
      <text x={col[0] + 10} y={mid + 4} fill="#fff" fontSize="13" fontWeight="700">{lead.name?.slice(0, 20)}</text>
      <text x={col[0] + 10} y={mid + 20} fill="#cbd5e1" fontSize="11">score {Math.round(lead.score)} · {p0(lead.probability)} if not contacted</text>
      {/* team step */}
      {box(col[1], mid - 30, nodeW, 60, 'rgba(249,115,22,0.12)', 'rgba(249,115,22,0.6)')}
      <text x={col[1] + 10} y={mid - 12} fill="#fdba74" fontSize="10">TEAM DOES</text>
      <text x={col[1] + 10} y={mid + 4} fill="#fff" fontSize="12" fontWeight="700">{step.label.slice(0, 27)}</text>
      <text x={col[1] + 10} y={mid + 20} fill="#cbd5e1" fontSize="11">{p0(step.p_buy_step)} buy in 14 days</text>
      {/* reactions + next steps */}
      {rs.map((r, i) => (
        <g key={`n${i}`}>
          {box(col[2], ys[i] - 24, nodeW, 48, 'rgba(255,255,255,0.04)', REACT_COLOR[r.reaction] || '#64748b')}
          <text x={col[2] + 10} y={ys[i] - 7} fill="#fff" fontSize="11" fontWeight="600">{r.label}</text>
          <text x={col[2] + 10} y={ys[i] + 9} fill="#94a3b8" fontSize="10">{p0(r.prob)} likely · then score {Math.round(r.next?.score ?? 0)} ({r.next?.stage})</text>
          {box(col[3], ys[i] - 24, nodeW, 48, 'rgba(56,189,248,0.07)', 'rgba(56,189,248,0.35)')}
          <text x={col[3] + 10} y={ys[i] - 10} fill="#7dd3fc" fontSize="9">BEST NEXT STEP</text>
          <text x={col[3] + 10} y={ys[i] + 4} fill="#fff" fontSize="11" fontWeight="600">{r.best_next?.label?.slice(0, 27)}</text>
          <text x={col[3] + 10} y={ys[i] + 17} fill="#94a3b8" fontSize="10">{p0(r.best_next?.p_buy)} chance they buy</text>
        </g>
      ))}
    </svg>
  )
}

function Note({ text }) {
  if (!text) return null
  const bad = text.startsWith('⚠️')
  return <p className={`text-sm px-3 py-2 rounded-xl border ${bad ? 'text-red-300 bg-red-900/20 border-red-800/30' : 'text-green-300 bg-green-900/20 border-green-800/30'}`}>{text}</p>
}

export default function LeadDetail() {
  const { id } = useParams()
  const [lead, setLead] = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState('action')
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [waMsg, setWaMsg] = useState('')
  const [coach, setCoach] = useState(null)
  const [busy, setBusy] = useState('')
  const [msg, setMsg] = useState({})
  const [coupon, setCoupon] = useState({ pct: 10, hours: 72 })
  const [explain, setExplain] = useState(null)
  const [attribution, setAttribution] = useState(null)
  const [paths, setPaths] = useState(null)
  const [pathsErr, setPathsErr] = useState('')
  const [pick, setPick] = useState(null)

  const note = (k, t) => setMsg(m => ({ ...m, [k]: t }))

  function load() {
    return getLead(id).then(r => {
      setLead(r.data)
      setSubject(s => s || r.data.email_subject || '')
      setBody(b => b || r.data.email_body || '')
      setWaMsg(w => w || r.data.whatsapp_message || '')
    }).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [id])   // eslint-disable-line react-hooks/exhaustive-deps

  async function improve() {
    setBusy('improve')
    try {
      const r = await aiImprove({ draft: body, subject, tier: lead.recommended_action, course: lead.course_type,
        course_slug: lead.course_slug, occupation: lead.current_occupation || '', name: lead.name || '' })
      setSubject(r.data.improved_subject); setBody(r.data.improved_body); setCoach(r.data)
    } catch { note('email', '⚠️ Could not improve the email') }
    finally { setBusy('') }
  }

  async function send() {
    setBusy('send'); note('email', '')
    try {
      const r = await sendEmail({ lead_id: Number(id), subject, body })
      note('email', (r.data.success ? '✅ ' : '⚠️ ') + r.data.message)
      if (r.data.success) load()
    } catch (e) { note('email', '⚠️ ' + (e.response?.data?.detail || 'Error')) }
    finally { setBusy('') }
  }

  async function openWhatsApp() {
    note('wa', '')
    try {
      const r = await whatsappLink({ lead_id: Number(id), message: waMsg })
      window.open(r.data.url, '_blank', 'noopener')
      note('wa', '✅ ' + r.data.message)
    } catch (e) { note('wa', '⚠️ ' + (e.response?.data?.detail || 'Error')) }
  }

  async function makeCoupon() {
    setBusy('coupon')
    try {
      const r = await generateCoupon({ user_id: lead.user_id, tier: lead.recommended_action, discount_pct: Number(coupon.pct), expires_hours: Number(coupon.hours) })
      note('coupon', '✅ ' + r.data.message); load()
    } catch (e) { note('coupon', '⚠️ ' + (e.response?.data?.detail || 'Error')) }
    finally { setBusy('') }
  }

  async function rescore() {
    setBusy('rescore')
    try { await rescoreLead(id); await load(); setExplain(null); note('top', '✅ Re-scored with the current model.') }
    catch (e) { note('top', '⚠️ ' + (e.response?.data?.detail || 'Rescore failed')) }
    finally { setBusy('') }
  }

  async function doneCallback(cbId) {
    await closeCallback(cbId).catch(() => {}); load()
  }

  function selectTab(key) {
    setTab(key)
    if (key === 'explain' && !explain) getLeadExplain(id).then(r => setExplain(r.data)).catch(() => {})
    if (key === 'attribution' && !attribution) getLeadAttribution(id).then(r => setAttribution(r.data)).catch(() => {})
    if (key === 'paths' && !paths) loadPaths()
  }

  function loadPaths() {
    setPathsErr('')
    getLeadPaths(id, 3).then(r => { setPaths(r.data); setPick(r.data.best) })
      .catch(e => setPathsErr(e.response?.data?.detail || 'Could not work out the paths for this lead.'))
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin" /></div>
  if (!lead) return <p className="text-slate-500 text-center mt-20">Lead not found.</p>

  const SC = s => s >= 80 ? 'text-red-400' : s >= 60 ? 'text-orange-400' : s >= 40 ? 'text-yellow-400' : 'text-slate-400'
  const openCallbacks = (lead.callbacks || []).filter(c => c.status === 'open')
  const tabs = [
    ['action', 'Recommended action'], ['paths', 'What-if paths'], ['email', 'Email'], ['whatsapp', 'WhatsApp'], ['activity', 'Activity'],
    ['chat', `Chat & callbacks${openCallbacks.length ? ` (${openCallbacks.length})` : ''}`], ['coupon', 'Coupon'],
    ['explain', 'Why this score?'], ['attribution', 'Attribution'],
  ]

  return (
    <div>
      <div className="flex flex-wrap items-center gap-4 mb-2">
        <Link to="/leads" className="text-slate-500 hover:text-white text-sm">← Back to Leads</Link>
        <h1 className="font-display text-2xl font-bold text-white">{lead.name}</h1>
        <span className={`font-display text-3xl font-extrabold ${SC(lead.lead_score)}`}>{Math.round(lead.lead_score)}<span className="text-slate-600 text-base font-normal">/100</span></span>
        <span className="text-xs px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-slate-300">{lead.recommended_action}</span>
        {lead.email?.endsWith('@demo.xeducation.test') && <span className="text-xs px-2.5 py-1 rounded-full bg-white/10 text-slate-400" title="Part of the simulated starting history; outcomes come from the simulator">simulated learner</span>}
        {lead.global_control && <span className="text-xs px-2.5 py-1 rounded-full bg-sky-500/10 border border-sky-500/30 text-sky-300" title="A fixed random 5% of leads never get automatic follow-ups. They show what happens without the CRM, and the learning loop checks every new model on them. Contacting them by hand mixes that up.">control group · no automatic follow-ups</span>}
        <button onClick={rescore} disabled={busy === 'rescore'} className="ml-auto text-xs border border-white/15 text-slate-300 rounded-lg px-3 py-1.5 hover:border-white/40 disabled:opacity-50">
          {busy === 'rescore' ? 'Re-scoring…' : '↻ Re-score now'}
        </button>
      </div>
      <div className="mb-6"><Note text={msg.top} /></div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card p-6 space-y-3 text-sm h-fit">
          <h3 className="font-display font-semibold text-white mb-2">Profile</h3>
          {[
            ['Email', lead.email], ['Phone', lead.phone || '—'], ['Occupation', lead.current_occupation || '—'],
            ['Specializ.', lead.specialization || '—'], ['City', lead.city || '—'], ['Age', lead.age_bracket || '—'],
            ['Course', lead.course_type || '—'], ['Persona', lead.persona], ['Trigger', lead.trigger_reason],
            ['Conv. prob.', `${((lead.conversion_probability || 0) * 100).toFixed(1)}%`],
            ['Exp. value', `₹${Math.round(lead.plv || 0).toLocaleString()}`],
            ['Purchases', lead.purchases?.length || 0],
            ['Email OK', lead.do_not_email === 'Yes' ? 'Opted out' : 'Yes'],
            ['Calls OK', lead.do_not_call === 'Yes' ? 'Opted out' : 'Yes'],
            ['WhatsApp', lead.whatsapp_opt_in ? 'Opted in' : '—'],
            ['Model', lead.model_version || '—'],
          ].map(([k, v]) => (
            <div key={k} className="flex gap-2">
              <span className="text-slate-500 w-24 flex-shrink-0">{k}</span>
              <span className="text-slate-200 break-all font-medium">{v}</span>
            </div>
          ))}
          {lead.touches?.length > 1 && (
            <div className="pt-3 border-t border-white/10">
              <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide mb-2">Touchpoints ({lead.touches.length})</p>
              {lead.touches.slice(0, 8).map(t => (
                <Link key={t.id} to={`/leads/${t.id}`} className={`flex justify-between text-xs py-1 ${String(t.id) === String(id) ? 'text-white' : 'text-slate-400 hover:text-white'}`}>
                  <span>{t.trigger_reason}</span><span>{Math.round(t.lead_score)} · {fmt(t.created_at)}</span>
                </Link>
              ))}
            </div>
          )}
        </div>

        <div className="lg:col-span-2 space-y-4">
          <div className="flex gap-2 flex-wrap">
            {tabs.map(([key, label]) => (
              <button key={key} onClick={() => selectTab(key)}
                className={`px-3.5 py-2 rounded-xl text-sm font-medium transition-all ${tab === key ? 'bg-ember text-white' : 'bg-white/5 border border-white/10 text-slate-400 hover:border-white/30'}`}>
                {label}
              </button>
            ))}
          </div>

          {tab === 'action' && (
            <div className="card p-6 space-y-4">
              <h3 className="font-display font-semibold text-white">Recommended action</h3>
              {lead.nba ? (
                <>
                  <div className="bg-ember/10 border border-ember/30 rounded-xl p-4">
                    <p className="text-white font-semibold">{lead.nba.label}</p>
                    <p className="text-slate-300 text-sm mt-1">{lead.nba.why}</p>
                    <p className="text-slate-500 text-xs mt-2">{lead.nba.detail}</p>
                  </div>
                  {lead.nba.options?.length > 0 && (
                    <table className="w-full text-xs">
                      <thead><tr className="text-slate-500 text-left"><th className="py-1">Action</th><th>P(buy)</th><th>Uplift</th><th>Exp. profit</th></tr></thead>
                      <tbody>{lead.nba.options.map(o => (
                        <tr key={o.action} className={`border-t border-white/5 ${o.action === lead.nba.action ? 'text-white' : 'text-slate-400'}`}>
                          <td className="py-1.5">{o.label}{o.blocked ? ` (${o.blocked})` : ''}</td>
                          <td>{(o.p_convert * 100).toFixed(1)}%</td>
                          <td>{o.uplift >= 0 ? '+' : ''}{(o.uplift * 100).toFixed(1)} pts</td>
                          <td>₹{Math.round(o.expected_profit).toLocaleString()}</td>
                        </tr>))}</tbody>
                    </table>
                  )}
                </>
              ) : <p className="text-slate-400 text-sm">No action computed for this lead yet — click “Re-score now”.</p>}
              {lead.tips?.length > 0 && (
                <div>
                  <p className="text-slate-400 text-xs uppercase tracking-wide font-semibold mb-2">How to move this lead up</p>
                  <div className="space-y-2">
                    {lead.tips.map((t, i) => (
                      <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-3">
                        <p className="text-white text-sm font-medium">{t.title}</p>
                        <p className="text-slate-400 text-xs mt-0.5">{t.detail}</p>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === 'email' && (
            <div className="card p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="font-display font-semibold text-white">Email editor</h3>
                <button onClick={improve} disabled={busy === 'improve'} className="px-4 py-2 bg-violet-600 hover:bg-violet-700 text-white rounded-xl text-sm font-medium disabled:opacity-60">
                  {busy === 'improve' ? 'Checking…' : 'Improve email'}
                </button>
              </div>
              <div><label className="lbl">Subject</label><input value={subject} onChange={e => setSubject(e.target.value)} className="inp" /></div>
              <div><label className="lbl">Body</label><textarea value={body} onChange={e => setBody(e.target.value)} rows={12} className="inp font-mono text-xs leading-relaxed" />
                <p className="text-slate-600 text-[11px] mt-1">Placeholders: {'{first_name}'}, {'{course}'}. The email gets a tracked button to the course page and an unsubscribe link.</p></div>
              {coach && (
                <div className="bg-violet-900/20 border border-violet-700/30 rounded-xl p-3">
                  <p className="text-violet-300 text-xs font-semibold mb-1">{coach.note}</p>
                  <ul className="list-disc pl-5 text-xs text-slate-300 space-y-0.5">{coach.suggestions.map(s => <li key={s}>{s}</li>)}</ul>
                </div>
              )}
              <Note text={msg.email} />
              {lead.do_not_email === 'Yes'
                ? <p className="text-red-300 text-sm text-center">This person has unsubscribed from emails.</p>
                : <button onClick={send} disabled={busy === 'send'} className="w-full btn disabled:opacity-60">
                    {busy === 'send' ? 'Sending…' : lead.email_sent ? `Send another email (last sent ${fmt(lead.email_sent_at)})` : 'Send email'}
                  </button>}
            </div>
          )}

          {tab === 'whatsapp' && (
            <div className="card p-6 space-y-4">
              <h3 className="font-display font-semibold text-white">WhatsApp</h3>
              <textarea value={waMsg} onChange={e => setWaMsg(e.target.value)} rows={5} maxLength={700} className="inp text-sm" />
              <p className="text-slate-500 text-xs">Opens WhatsApp (web or app) with this message ready to send to {lead.phone || 'the lead'} — free, no API needed. Only allowed if the person opted in.</p>
              <Note text={msg.wa} />
              <button onClick={openWhatsApp} disabled={!lead.whatsapp_opt_in} className="w-full btn disabled:opacity-50">
                {lead.whatsapp_opt_in ? 'Open in WhatsApp' : 'Not opted in to WhatsApp'}
              </button>
              {lead.call_script && (
                <div className="pt-4 border-t border-white/10">
                  <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide mb-2">Call script</p>
                  <p className="text-slate-300 text-sm leading-relaxed">{lead.call_script}</p>
                </div>
              )}
            </div>
          )}

          {tab === 'activity' && (
            <div className="card p-6 space-y-6">
              <div className="grid grid-cols-3 gap-3">
                {[
                  ['Visits', lead.total_visits], ['Time on site', `${Math.round((lead.total_time_on_website || 0) / 60)} min`],
                  ['Pages / visit', lead.page_views_per_visit], ['Email clicks', lead.email_opened_count],
                  ['Source', lead.lead_source || '—'], ['Device', lead.device_type || '—'],
                  ['Video', yes(lead.video_watched)], ['Brochure', yes(lead.brochure_downloaded)], ['Chat', yes(lead.chat_initiated)],
                  ['Pricing', yes(lead.pricing_page_visited)], ['Testimonials', yes(lead.testimonial_visited)], ['Webinar', yes(lead.webinar_attended)],
                ].map(([k, v]) => (
                  <div key={k} className="bg-white/5 rounded-xl px-3 py-2.5"><p className="text-slate-500 text-xs">{k}</p><p className="text-white font-semibold text-sm">{v}</p></div>
                ))}
              </div>
              {lead.emails?.length > 0 && (
                <div>
                  <h4 className="text-slate-400 text-xs uppercase tracking-wide mb-2 font-semibold">Emails</h4>
                  {lead.emails.map(e => (
                    <div key={e.id} className="flex justify-between gap-3 text-xs py-1 border-b border-white/5">
                      <span className="text-slate-300 truncate">{e.subject}</span>
                      <span className="text-slate-500 flex-shrink-0">{fmt(e.sent_at)} · {e.click_count ? '✅ clicked' : 'no click yet'}</span>
                    </div>
                  ))}
                </div>
              )}
              {lead.score_history?.length > 0 && (
                <div>
                  <h4 className="text-slate-400 text-xs uppercase tracking-wide mb-2 font-semibold">Score history</h4>
                  {lead.score_history.map(h => (
                    <div key={h.id} className="flex justify-between text-xs py-1 text-slate-400">
                      <span>{h.reason}</span><span>{Math.round(h.old_score)} → {Math.round(h.new_score)} · {fmt(h.created_at)}</span>
                    </div>
                  ))}
                </div>
              )}
              {lead.behaviour_events?.length > 0 && (
                <div>
                  <h4 className="text-slate-400 text-xs uppercase tracking-wide mb-2 font-semibold">Recent events</h4>
                  <div className="space-y-1.5 max-h-56 overflow-y-auto">
                    {lead.behaviour_events.map(e => (
                      <div key={e.id} className="flex items-center gap-3 text-xs text-slate-400">
                        <span className="w-28 flex-shrink-0 text-slate-600">{fmt(e.created_at)}</span>
                        <span className="bg-white/5 px-2 py-0.5 rounded-full">{e.event_type}</span>
                        {e.course_slug && <span className="text-slate-600">{e.course_slug}</span>}
                        {e.time_spent_sec > 0 && <span className="text-slate-600">{e.time_spent_sec}s</span>}
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {tab === 'chat' && (
            <div className="card p-6 space-y-5">
              <div>
                <h3 className="font-display font-semibold text-white mb-3">Callback requests</h3>
                {!lead.callbacks?.length ? <p className="text-slate-500 text-sm">None.</p> : lead.callbacks.map(c => (
                  <div key={c.id} className="flex items-center justify-between gap-3 bg-white/5 rounded-xl px-3 py-2 mb-2 text-sm">
                    <span className="text-slate-200">{c.phone} · {c.preferred_time || 'any time'} <span className="text-slate-500 text-xs">({fmt(c.created_at)})</span></span>
                    {c.status === 'open'
                      ? <button onClick={() => doneCallback(c.id)} className="text-xs text-sky-accent hover:underline">Mark called</button>
                      : <span className="text-xs text-green-400">Done</span>}
                  </div>
                ))}
              </div>
              <div>
                <h3 className="font-display font-semibold text-white mb-3">Chat transcript</h3>
                {!lead.chat?.length ? <p className="text-slate-500 text-sm">No chat yet.</p> : (
                  <div className="space-y-2 max-h-80 overflow-y-auto">
                    {lead.chat.map((m, i) => (
                      <div key={i} className={`text-xs ${m.role === 'user' ? 'text-white' : 'text-slate-400'}`}>
                        <span className="font-semibold">{m.role === 'user' ? lead.name.split(' ')[0] : 'Assistant'}:</span> {m.text}
                        <span className="text-slate-600"> · {m.intent}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {tab === 'coupon' && (
            <div className="card p-6 space-y-4">
              <h3 className="font-display font-semibold text-white">Personal coupon</h3>
              <p className="text-slate-400 text-xs">Creates a unique code that only this person can use. Tip: the “Recommended action” tab shows whether a discount is likely to change their decision at all.</p>
              <div className="grid grid-cols-2 gap-3">
                <div><label className="lbl">Discount %</label><input type="number" min={5} max={50} value={coupon.pct} onChange={e => setCoupon(c => ({ ...c, pct: e.target.value }))} className="inp" /></div>
                <div><label className="lbl">Valid for (hours)</label><input type="number" min={1} max={720} value={coupon.hours} onChange={e => setCoupon(c => ({ ...c, hours: e.target.value }))} className="inp" /></div>
              </div>
              <Note text={msg.coupon} />
              <button onClick={makeCoupon} disabled={busy === 'coupon'} className="w-full btn disabled:opacity-60">{busy === 'coupon' ? 'Generating…' : 'Generate & assign'}</button>
              {lead.coupons?.length > 0 && (
                <div className="pt-4 border-t border-white/10">
                  {lead.coupons.map(c => (
                    <div key={c.id} className="flex items-center justify-between text-xs py-1.5">
                      <span className="font-mono text-ember">{c.coupon_code}</span>
                      <span className="text-slate-400">{c.discount_pct}% off</span>
                      <span className="text-slate-500">exp. {fmt(c.expires_at)}</span>
                      <span className={c.used ? 'text-slate-600' : 'text-green-400'}>{c.used ? 'Used' : 'Active'}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'paths' && (
            <div className="card p-6 space-y-5">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h3 className="font-display font-semibold text-white">What-if paths</h3>
                  <p className="text-slate-500 text-xs mt-1 max-w-2xl">If the team takes a step now, how is this learner likely to react in the next 3 days, and what is
                    the best step after that? Chances to buy come from this lead's own models; the reactions are what similar leads did after
                    the same step in the CRM's history.</p>
                </div>
                <button onClick={() => { setPaths(null); loadPaths() }} className="text-xs border border-white/15 text-slate-300 rounded-lg px-3 py-1.5 hover:border-white/40 whitespace-nowrap">↻ Refresh</button>
              </div>
              {pathsErr && <p className="text-red-400 text-sm">{pathsErr}</p>}
              {!paths && !pathsErr && <p className="text-slate-500 text-sm">Working out the paths…</p>}
              {paths && (
                <>
                  {paths.summary && <div className="bg-ember/10 border border-ember/30 rounded-xl p-4"><p className="text-white text-sm">{paths.summary}</p></div>}
                  <div>
                    <p className="text-slate-400 text-xs uppercase tracking-wide font-semibold mb-2">Step 1 — what the team can do now (click one)</p>
                    <div className="grid sm:grid-cols-2 gap-2">
                      {paths.steps.map(st => (
                        <button key={st.action} onClick={() => setPick(st.action)}
                          className={`text-left rounded-xl border p-3 transition-all ${pick === st.action ? 'border-ember bg-ember/10' : 'border-white/10 bg-white/5 hover:border-white/30'}`}>
                          <div className="flex justify-between gap-2">
                            <span className="text-white text-sm font-semibold">{st.label}</span>
                            {st.action === paths.best && <span className="text-[10px] text-green-400 border border-green-500/40 rounded-full px-2 py-0.5 h-fit">best</span>}
                          </div>
                          <p className="text-slate-300 text-xs mt-1">{p0(st.p_buy_path)} chance to buy on this path (this step, then the best next one)
                            {st.gain_vs_nothing != null && st.action !== 'none' ? ` · ${st.gain_vs_nothing >= 0 ? '+' : '−'}${inr(Math.abs(st.gain_vs_nothing))} vs waiting` : ''}</p>
                          <p className="text-slate-600 text-[11px]">from {st.evidence.decisions} past decisions for {st.evidence.stage} leads</p>
                        </button>
                      ))}
                    </div>
                  </div>
                  {(() => {
                    const st = paths.steps.find(x => x.action === pick) || paths.steps[0]
                    if (!st) return null
                    const after = st.then && (st.reactions || []).find(r => r.reaction === st.then.after)
                    return (
                      <div>
                        <p className="text-slate-400 text-xs uppercase tracking-wide font-semibold mb-2">If the team chooses “{st.label}”</p>
                        <PathTree lead={paths.lead} step={st} />
                        {st.then && after && (
                          <p className="text-slate-300 text-xs mt-2">Three steps ahead: if they {after.label.toLowerCase()} and the team then {after.best_next.label.toLowerCase()},
                            the likeliest reaction is “{st.then.reaction2_label.toLowerCase()}”; the best third step is {st.then.step3_label.toLowerCase()} ({p0(st.then.p_buy)} chance to buy).</p>
                        )}
                      </div>
                    )
                  })()}
                  {Object.keys(paths.blocked || {}).length > 0 && (
                    <p className="text-slate-500 text-xs">Not possible now: {Object.entries(paths.blocked).map(([a, why]) => `${a.replaceAll('_', ' ')} (${why})`).join(' · ')}</p>
                  )}
                  <p className="text-slate-500 text-[11px]">{paths.note} History used: {paths.history?.decisions?.toLocaleString?.() ?? 0} decisions
                    ({paths.history?.stage_decisions ?? 0} for {paths.lead.stage} leads).</p>
                </>
              )}
            </div>
          )}

          {tab === 'explain' && (
            <div className="card p-6">
              <h3 className="font-display font-semibold text-white mb-1">Why this score?</h3>
              <p className="text-slate-500 text-xs mb-4">Each line shows how many points the score would change without that signal (computed by the model).
                The score is the chance this person buys within 14 days if we do nothing now.</p>
              {!explain ? <p className="text-slate-500 text-sm">Loading…</p> : (
                <div className="space-y-2">
                  {explain.note && <p className="text-slate-400 text-sm">{explain.note}</p>}
                  {explain.factors.map((f, i) => (
                    <div key={i} className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 flex items-center justify-between gap-3">
                      <div><p className="text-white font-semibold text-sm">{f.factor}</p><p className="text-slate-400 text-xs">{f.detail}</p></div>
                      <span className={`font-mono text-sm flex-shrink-0 ${(f.points ?? 0) < 0 ? 'text-red-400' : 'text-green-400'}`}>{f.impact}</span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}

          {tab === 'attribution' && (
            <div className="card p-6">
              <h3 className="font-display font-semibold text-white mb-4">Path to conversion</h3>
              {!attribution ? <p className="text-slate-500 text-sm">Loading…</p> : (
                <>
                  <div className="grid grid-cols-2 gap-3 mb-6">
                    <div className="bg-white/5 rounded-xl px-3 py-2.5"><p className="text-slate-500 text-xs">First touch</p><p className="text-white font-semibold text-sm">{attribution.first_touch?.label || '—'}</p></div>
                    <div className="bg-white/5 rounded-xl px-3 py-2.5"><p className="text-slate-500 text-xs">Last touch before purchase</p><p className="text-white font-semibold text-sm">{attribution.last_touch_before_purchase?.label || (attribution.converted ? '—' : 'Not converted yet')}</p></div>
                  </div>
                  <div className="space-y-2 max-h-72 overflow-y-auto">
                    {attribution.timeline.map((t, i) => (
                      <div key={i} className="flex items-center gap-3 text-xs text-slate-400">
                        <span className="w-32 flex-shrink-0 text-slate-600">{fmt(t.created_at)}</span>
                        <span className="bg-white/5 px-2 py-0.5 rounded-full">{t.kind}</span>
                        <span className="text-slate-300">{t.label}</span>
                        {t.course_slug && <span className="text-slate-600">{t.course_slug}</span>}
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
