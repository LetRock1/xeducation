import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import {
  getLead, sendEmail, aiImprove, whatsappLink, generateCoupon, getLeadExplain,
  getLeadAttribution, closeCallback, getLeadPaths, getLeadNow, leadAct,
} from '../utils/api'
import { stageLabel, triggerLabel, reasonLabel, daysText } from '../utils/labels'

const fmt = d => d ? new Date(String(d).replace(' ', 'T')).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '—'
const yes = v => v ? 'Yes' : '—'
const p0 = x => (x == null ? '—' : `${(x * 100).toFixed(0)}%`)
const p1 = x => (x == null ? '—' : `${(x * 100).toFixed(1)}%`)
const pts = x => (x == null ? '—' : `${x >= 0 ? '+' : '−'}${Math.abs(x * 100).toFixed(1)} pts`)
const inr = x => (x == null ? '—' : `${x < 0 ? '−' : ''}₹${Math.abs(Math.round(x)).toLocaleString('en-IN')}`)
const REACT_COLOR = { bought: '#22c55e', advanced: '#22c55e', engaged: '#38BDF8', clicked: '#a78bfa', none: '#64748b' }
const DO_LABEL = {
  email_info: 'Send the information email now', email_coupon_10: 'Send the email with a 10% coupon now',
  email_coupon_20: 'Send the email with a 20% coupon now', call: 'Add the call to Today\'s actions',
  whatsapp: 'Add the WhatsApp message to Today\'s actions',
}

/* One team step → the learner's likely reactions in 3 days → the best next step after each (history + models). */
function PathTree({ lead, step }) {
  const rs = step.reactions || []
  const W = 820, nodeW = 178, rowH = 66, H = Math.max(rs.length, 1) * rowH + 24
  const col = [8, 214, 420, 632]
  const ys = rs.map((_, i) => 12 + i * rowH + rowH / 2 - 6)
  const mid = H / 2
  const box = (x, y, w, h, fill, stroke) => <rect x={x} y={y} width={w} height={h} rx="10" fill={fill} stroke={stroke} />
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label="What-if path tree">
      <path d={`M${col[0] + nodeW},${mid} L${col[1]},${mid}`} stroke="#f97316" strokeWidth="3" fill="none" />
      {rs.map((r, i) => (
        <g key={`e${i}`}>
          <path d={`M${col[1] + nodeW},${mid} C${col[1] + nodeW + 20},${mid} ${col[2] - 20},${ys[i]} ${col[2]},${ys[i]}`}
            stroke={REACT_COLOR[r.reaction] || '#64748b'} strokeOpacity="0.8" strokeWidth={Math.max(1.5, r.prob * 14)} fill="none" />
          {r.best_next && <path d={`M${col[2] + nodeW},${ys[i]} L${col[3]},${ys[i]}`} stroke="#475569" strokeWidth="1.5" strokeDasharray="4 3" fill="none" />}
        </g>
      ))}
      {box(col[0], mid - 30, nodeW, 60, 'rgba(255,255,255,0.05)', 'rgba(255,255,255,0.15)')}
      <text x={col[0] + 10} y={mid - 12} fill="#94a3b8" fontSize="10">NOW · {stageLabel(lead.stage)}</text>
      <text x={col[0] + 10} y={mid + 4} fill="#fff" fontSize="13" fontWeight="700">{lead.name?.slice(0, 20)}</text>
      <text x={col[0] + 10} y={mid + 20} fill="#cbd5e1" fontSize="11">{p0(lead.probability)} chance if we do nothing</text>
      {box(col[1], mid - 30, nodeW, 60, 'rgba(249,115,22,0.12)', 'rgba(249,115,22,0.6)')}
      <text x={col[1] + 10} y={mid - 12} fill="#fdba74" fontSize="10">TEAM DOES</text>
      <text x={col[1] + 10} y={mid + 4} fill="#fff" fontSize="12" fontWeight="700">{step.label.slice(0, 27)}</text>
      <text x={col[1] + 10} y={mid + 20} fill="#cbd5e1" fontSize="11">{p0(step.p_buy_step)} chance to buy in 14 days</text>
      {rs.map((r, i) => (
        <g key={`n${i}`}>
          {box(col[2], ys[i] - 24, nodeW, 48, 'rgba(255,255,255,0.04)', REACT_COLOR[r.reaction] || '#64748b')}
          <text x={col[2] + 10} y={ys[i] - 7} fill="#fff" fontSize="11" fontWeight="600">{r.label}</text>
          <text x={col[2] + 10} y={ys[i] + 9} fill="#94a3b8" fontSize="10">{p0(r.prob)} likely{r.next ? ` · then score ${Math.round(r.next.score)}` : ''}</text>
          {r.best_next && <>
            {box(col[3], ys[i] - 24, nodeW, 48, 'rgba(56,189,248,0.07)', 'rgba(56,189,248,0.35)')}
            <text x={col[3] + 10} y={ys[i] - 10} fill="#7dd3fc" fontSize="9">THEN THE CRM WOULD</text>
            <text x={col[3] + 10} y={ys[i] + 4} fill="#fff" fontSize="11" fontWeight="600">{r.best_next.label?.slice(0, 27)}</text>
            <text x={col[3] + 10} y={ys[i] + 17} fill="#94a3b8" fontSize="10">{p0(r.best_next.p_buy)} chance they buy</text>
          </>}
        </g>
      ))}
    </svg>
  )
}

/* What the CRM would do right now, with the full receipt (same numbers the automatic decisions use). */
function NowCard({ now, err, lead, busy, onAct }) {
  if (err) return <div className="card p-6"><p className="text-red-400 text-sm">{err}</p></div>
  if (!now) return <div className="card p-6"><p className="text-slate-500 text-sm">Working out the best step for right now…</p></div>
  if (!now.recommendation) {
    return (
      <div className="card p-6 space-y-3">
        <h3 className="font-display font-semibold text-white">Customer</h3>
        <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4 space-y-1">
          {(now.purchases || []).map((p, i) => (
            <p key={i} className="text-white text-sm">✓ Bought <b>{p.course}</b> on {fmt(p.at)} · paid {inr(p.paid)}{p.coupon ? ` (coupon ${p.coupon})` : ''}</p>
          ))}
          <p className="text-slate-300 text-xs pt-1">{now.message}</p>
        </div>
      </div>
    )
  }
  const rec = now.recommendation
  const opts = now.options || []
  const canAct = !now.control_group
  return (
    <div className="card p-6 space-y-4">
      <div>
        <h3 className="font-display font-semibold text-white">If the team acts now, the CRM recommends</h3>
        <p className="text-slate-500 text-xs mt-1">For {now.course?.title || 'our programmes'} ({inr(now.course?.price)}) · chance to buy within 14 days
          if we do nothing: <span className="text-slate-300">{p1(now.probability)}</span> · last on the site {daysText(now.away_days)}</p>
      </div>
      <div className="bg-ember/10 border border-ember/30 rounded-xl p-4">
        <p className="text-white font-semibold text-lg">{rec.label}</p>
        <p className="text-slate-300 text-sm mt-1">{rec.why}</p>
        {rec.action !== 'none' && (
          <button onClick={() => onAct(rec.action)} disabled={!canAct || !!busy}
            className="btn text-sm mt-3 disabled:opacity-50">{busy === rec.action ? 'Working…' : `▶ Do it now: ${DO_LABEL[rec.action] || rec.label}`}</button>
        )}
        {now.control_group && <p className="text-sky-300 text-xs mt-2">In the 5% control group: the CRM never contacts this person, so “Do it now” is off. What they do on their own is the honest check for the learning loop.</p>}
      </div>
      <div>
        <p className="text-slate-400 text-xs uppercase tracking-wide font-semibold mb-2">The receipt: every step, worked out for this person now</p>
        <table className="w-full text-xs">
          <thead><tr className="text-slate-500 text-left"><th className="py-1">Step</th><th>Chance to buy<br/>in 14 days</th><th>Change vs<br/>doing nothing</th><th>Extra profit vs<br/>doing nothing</th><th></th></tr></thead>
          <tbody>{opts.map(o => (
            <tr key={o.action} className={`border-t border-white/5 ${o.action === rec.action ? 'text-white font-semibold' : o.blocked ? 'text-slate-600' : 'text-slate-300'}`}>
              <td className="py-1.5">{o.label}{o.action === rec.action ? ' ✓' : ''}{o.blocked ? <span className="block text-[10px] font-normal">not possible: {o.blocked}</span> : null}</td>
              <td>{p1(o.p_convert)}</td>
              <td>{o.action === 'none' ? '—' : pts(o.uplift)}</td>
              <td className={o.incremental_profit > 0 ? 'text-green-400' : o.incremental_profit < 0 ? 'text-red-400' : ''}>{o.action === 'none' ? '₹0' : inr(o.incremental_profit)}</td>
              <td className="text-right">{!o.blocked && o.action !== 'none' && o.action !== rec.action && canAct &&
                <button onClick={() => onAct(o.action)} disabled={!!busy} className="text-[11px] border border-white/15 text-slate-300 rounded-lg px-2 py-1 hover:border-white/40 disabled:opacity-50">{busy === o.action ? '…' : 'Do this'}</button>}</td>
            </tr>))}</tbody>
        </table>
        <p className="text-slate-500 text-[11px] mt-2">How it is decided: the chance for each step comes from the next-best-action model ({now.nba_model}), anchored to
          this person's lead score (model {now.lead_model}). Extra profit = chance × course price × (1 − discount) − cost of the step, minus the same for doing
          nothing. The step with the highest extra profit wins; if none is above ₹0, the CRM does nothing. Automatic decisions use exactly this, except that
          15% of them are picked at random so the CRM keeps learning what really works.</p>
      </div>
      {(now.tips || []).length > 0 && (
        <div>
          <p className="text-slate-400 text-xs uppercase tracking-wide font-semibold mb-2">How this learner could move up (guidance)</p>
          <div className="space-y-2">{now.tips.map((t, i) => (
            <div key={i} className="bg-white/5 border border-white/10 rounded-xl p-3"><p className="text-white text-sm font-medium">{t.title}</p><p className="text-slate-400 text-xs mt-0.5">{t.detail}</p></div>
          ))}</div>
        </div>
      )}
    </div>
  )
}

function OutcomeChips({ x }) {
  const chips = []
  if (x.email) {
    chips.push(['✉️', `email sent ${fmt(x.email.sent_at)}`, 'text-slate-300'])
    chips.push(x.email.clicked_at ? ['🖱️', `clicked ${fmt(x.email.clicked_at)}`, 'text-green-400'] : ['🖱️', 'not clicked', 'text-slate-500'])
  }
  if (x.task) {
    const o = { reached: 'spoke to them', no_answer: 'no answer', not_interested: 'not interested', sent: 'sent' }[x.task.outcome]
    chips.push(['📞', x.task.status === 'open' ? `${x.task.type} task open in Today's actions` : `${x.task.type}: ${o || x.task.outcome}`, 'text-slate-300'])
  }
  if (x.next_visit) chips.push(['👀', `back on the site ${fmt(x.next_visit)}`, 'text-sky-300'])
  if (x.outcome === 'bought') chips.push(['💰', `bought ${x.bought.course} ${fmt(x.bought.at)} (within 14 days)`, 'text-green-400 font-semibold'])
  else if (x.outcome === 'did_not_buy') chips.push(['—', 'did not buy within 14 days', 'text-slate-500'])
  else chips.push(['⏳', `waiting: ${x.days_left} day(s) left in the 14-day window`, 'text-slate-500'])
  return <div className="flex flex-wrap gap-x-4 gap-y-1 mt-1.5">{chips.map(([i, t, c], k) => <span key={k} className={`text-[11px] ${c}`}>{i} {t}</span>)}</div>
}

/* Everything the CRM did (or chose not to do) for this person, with the receipt and what happened next. */
function History({ items }) {
  const [open, setOpen] = useState(null)
  if (!items?.length) return <div className="card p-6"><h3 className="font-display font-semibold text-white mb-1">What the CRM has done so far</h3><p className="text-slate-500 text-sm">Nothing yet: the CRM decides when the person leaves the site, leaves the cart or checkout, wishlists a course or sends an enquiry.</p></div>
  return (
    <div className="card p-6">
      <h3 className="font-display font-semibold text-white mb-1">What the CRM has done so far</h3>
      <p className="text-slate-500 text-xs mb-3">Each decision with its receipt, and what the learner did afterwards. Outcome = bought within 14 days.</p>
      <div className="space-y-2">
        {items.map((x, i) => (
          <div key={i} className="bg-white/5 border border-white/10 rounded-xl px-3 py-2.5">
            {x.kind === 'decision' ? (
              <>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-slate-500 text-xs w-28">{fmt(x.at)}</span>
                  <span className="text-slate-400 text-xs">{triggerLabel(x.trigger)} →</span>
                  <span className="text-white font-semibold">{x.label}</span>
                  <span className={`text-[10px] px-2 py-0.5 rounded-full border ${x.policy === 'explore' ? 'border-violet-500/40 text-violet-300' : x.policy === 'manual' ? 'border-ember/40 text-ember' : x.policy === 'holdout' ? 'border-sky-500/40 text-sky-300' : 'border-white/15 text-slate-400'}`}>{x.policy_text}</span>
                  {x.policy === 'explore' && x.model_best !== x.action && <span className="text-[11px] text-slate-500">model's own pick: {x.model_best_label}</span>}
                  {x.options?.length > 0 && <button onClick={() => setOpen(open === i ? null : i)} className="ml-auto text-[11px] text-sky-accent hover:underline">{open === i ? 'hide receipt' : 'receipt'}</button>}
                </div>
                {x.adopted_email && <p className="text-[11px] text-slate-500 mt-1">Email text: {x.adopted_email.arm === 'adopted'
                  ? `“${x.adopted_email.variant}”, the adopted winner of the A/B test “${x.adopted_email.test}”`
                  : `the old text (this person is in the 10% check group of the adopted A/B winner “${x.adopted_email.variant}”)`}</p>}
                <OutcomeChips x={x} />
                {open === i && (
                  <table className="w-full text-[11px] mt-2">
                    <thead><tr className="text-slate-500 text-left"><th className="py-1">Step</th><th>Chance to buy</th><th>Change</th><th>Extra profit</th></tr></thead>
                    <tbody>{x.options.map(o => (
                      <tr key={o.action} className={`border-t border-white/5 ${o.action === x.action ? 'text-white' : o.blocked ? 'text-slate-600' : 'text-slate-400'}`}>
                        <td className="py-1">{o.label}{o.action === x.model_best ? ' (model\'s pick)' : ''}{o.blocked ? ` — ${o.blocked}` : ''}</td>
                        <td>{p1(o.p_convert)}</td><td>{o.action === 'none' ? '—' : pts(o.uplift)}</td><td>{o.action === 'none' ? '₹0' : inr(o.incremental_profit)}</td>
                      </tr>))}</tbody>
                    <tfoot><tr><td colSpan={4} className="text-slate-600 pt-1">model {x.model_version} · course price {inr(x.price)} · probability of this choice {x.propensity != null ? `${(x.propensity * 100).toFixed(0)}%` : '—'}</td></tr></tfoot>
                  </table>
                )}
              </>
            ) : (
              <>
                <div className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="text-slate-500 text-xs w-28">{fmt(x.at)}</span>
                  <span className="text-slate-400 text-xs">{x.kind === 'ab' ? 'A/B test' : 'Campaign'} “{x.name}” →</span>
                  <span className="text-white font-semibold">{x.sent ? (x.kind === 'ab' ? `got variant ${x.arm}` : 'email sent') : 'held out on purpose (got nothing)'}</span>
                  <span className="text-[10px] px-2 py-0.5 rounded-full border border-white/15 text-slate-400">random assignment</span>
                </div>
                <OutcomeChips x={x} />
              </>
            )}
          </div>
        ))}
      </div>
    </div>
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
  const [now, setNow] = useState(null)
  const [nowErr, setNowErr] = useState('')

  const note = (k, t) => setMsg(m => ({ ...m, [k]: t }))

  function load() {
    return getLead(id).then(r => {
      setLead(r.data)
      setSubject(s => s || r.data.email_subject || '')
      setBody(b => b || r.data.email_body || '')
      setWaMsg(w => w || r.data.whatsapp_message || '')
    }).catch(() => {}).finally(() => setLoading(false))
  }
  function loadNow() {
    setNowErr('')
    return getLeadNow(id).then(r => setNow(r.data))
      .catch(e => setNowErr(e.response?.data?.detail || 'Could not work out the recommendation right now.'))
  }
  // the page keeps itself current (score, decisions, clicks): no button to press
  useEffect(() => {
    setNow(null); setPaths(null); setExplain(null)
    load(); loadNow()
    const t = setInterval(() => { load(); loadNow() }, 15000)
    return () => clearInterval(t)
  }, [id])   // eslint-disable-line react-hooks/exhaustive-deps

  async function act(action) {
    setBusy(action); note('act', '')
    try {
      const r = await leadAct(id, action)
      note('act', '✅ ' + r.data.message + (r.data.model_pick && r.data.model_pick !== r.data.action ? ` (the model's own pick was: ${r.data.model_pick.replaceAll('_', ' ')})` : ''))
      await load(); await loadNow(); setPaths(null)
      if (tab === 'paths') loadPaths()
    } catch (e) { note('act', '⚠️ ' + (e.response?.data?.detail || 'Could not do it')) }
    finally { setBusy('') }
  }

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
    getLeadPaths(id, 2).then(r => { setPaths(r.data); setPick(r.data.best) })
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
  const customer = lead.customer
  const score = now?.score ?? lead.lead_score
  const firstBuy = (lead.purchases || [])[lead.purchases.length - 1]
  const profileRows = [
    ['Email', lead.email], ['Phone', lead.phone || '—'], ['Occupation', lead.current_occupation || '—'],
    ['Specializ.', lead.specialization || '—'], ['City', lead.city || '—'], ['Age', lead.age_bracket || '—'],
    ['Course', lead.course_type || '—'],
    ...(customer
      ? (lead.purchases || []).map(p => ['Bought', `${p.course_title} · ${fmt(p.purchased_at)} · ₹${Math.round(p.price_paid).toLocaleString('en-IN')}`])
          .concat([['Spent', `₹${Math.round(lead.spent || 0).toLocaleString('en-IN')}`]])
      : [['Chance to buy', `${((now?.probability ?? lead.conversion_probability) * 100 || 0).toFixed(1)}% within 14 days if we do nothing`],
         ['Exp. value', `₹${Math.round(lead.plv || 0).toLocaleString('en-IN')} (chance × course price)`]]),
    ['Last on site', daysText(now?.away_days)],
    ['Email OK', lead.do_not_email === 'Yes' ? 'Opted out' : 'Yes'],
    ['Calls OK', lead.do_not_call === 'Yes' ? 'Opted out' : 'Yes'],
    ['WhatsApp', lead.whatsapp_opt_in ? 'Opted in' : '—'],
    ['Model', now?.lead_model || lead.model_version || '—'],
  ]

  return (
    <div>
      <div className="flex flex-wrap items-center gap-4 mb-2">
        <Link to="/leads" className="text-slate-500 hover:text-white text-sm">← Back to Leads</Link>
        <h1 className="font-display text-2xl font-bold text-white">{lead.name}</h1>
        {customer ? (
          <span className="text-sm px-3 py-1 rounded-full bg-green-500/15 border border-green-500/40 text-green-300 font-semibold"
            title="A customer is not scored for the course they bought">✓ Customer{firstBuy ? ` since ${fmt(firstBuy.purchased_at)}` : ''}</span>
        ) : (
          <>
            <span className={`font-display text-3xl font-extrabold ${SC(score)}`} title="Chance (in %) that this person buys within 14 days if we do nothing now">
              {Math.round(score)}<span className="text-slate-600 text-base font-normal">/100</span></span>
            <span className="text-xs px-2.5 py-1 rounded-full bg-white/5 border border-white/10 text-slate-300">{now?.tier || lead.recommended_action}</span>
          </>
        )}
        {lead.simulated && <span className="text-xs px-2.5 py-1 rounded-full bg-white/10 text-slate-400" title="A simulated learner: uses the website by itself through the same API as a browser (documented simulator: visits, reactions to e-mails, coupons and calls, buying). E-mails to them are recorded, never delivered; their phone number is not real, so a simulated advisor handles their calls.">simulated learner</span>}
        {lead.global_control && <span className="text-xs px-2.5 py-1 rounded-full bg-sky-500/10 border border-sky-500/30 text-sky-300" title="A fixed random 5% of leads never get automatic follow-ups. They show what happens without the CRM, and the learning loop checks every new model on them. Contacting them by hand mixes that up.">control group · no automatic follow-ups</span>}
        <span className="ml-auto text-[11px] text-slate-500" title="Every event re-scores the person at once; every lead is also re-scored by itself every few minutes and whenever the learning loop switches models">score kept current automatically</span>
      </div>
      <div className="mb-6"><Note text={msg.act} /></div>

      <div className="grid lg:grid-cols-3 gap-6">
        <div className="card p-6 space-y-3 text-sm h-fit">
          <h3 className="font-display font-semibold text-white mb-2">Profile</h3>
          {profileRows.map(([k, v], i) => (
            <div key={`${k}${i}`} className="flex gap-2">
              <span className="text-slate-500 w-24 flex-shrink-0">{k}</span>
              <span className="text-slate-200 break-words min-w-0 font-medium">{v}</span>
            </div>
          ))}
          {lead.touches?.length > 1 && (
            <div className="pt-3 border-t border-white/10">
              <p className="text-slate-500 text-xs font-semibold uppercase tracking-wide mb-2">Touchpoints ({lead.touches.length}) · score at that time</p>
              {lead.touches.slice(0, 8).map(t => (
                <div key={t.id} className="flex justify-between text-xs py-1 text-slate-400">
                  <span>{triggerLabel(t.trigger_reason)}</span><span>{Math.round(t.lead_score)} · {fmt(t.created_at)}</span>
                </div>
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
            <div className="space-y-4">
              <NowCard now={now} err={nowErr} lead={lead} busy={busy} onAct={act} />
              <History items={lead.decisions} />
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
                      <span className="text-slate-300 truncate">{e.subject}{e.campaign_name ? <span className="text-slate-600"> · {e.campaign_name}</span> : null}</span>
                      <span className="text-slate-500 flex-shrink-0">{fmt(e.sent_at)} · {e.click_count ? <span className="text-green-400">✅ clicked {fmt(e.first_clicked_at)}</span> : 'no click yet'}</span>
                    </div>
                  ))}
                  <p className="text-slate-600 text-[11px] mt-1">The “View Course” button in each email opens that course on our website; the page reports the click, so it is tied to the exact email.</p>
                </div>
              )}
              {lead.score_history?.length > 0 && (
                <div>
                  <h4 className="text-slate-400 text-xs uppercase tracking-wide mb-2 font-semibold">Score history</h4>
                  {lead.score_history.map(h => (
                    <div key={h.id} className="flex justify-between text-xs py-1 text-slate-400">
                      <span>{reasonLabel(h.reason)}</span><span>{Math.round(h.old_score)} → {Math.round(h.new_score)} · {fmt(h.created_at)}</span>
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
                  <p className="text-slate-500 text-xs mt-1 max-w-2xl">If the team takes a step now, how is this learner likely to react in the next 3 days, and
                    what would the CRM do next? Step 1 has the same numbers and the same pick as the Recommended action tab. The reactions are what
                    learners in the same stage did after the same step in the CRM's history.</p>
                </div>
                <button onClick={() => { setPaths(null); loadPaths() }} className="text-xs border border-white/15 text-slate-300 rounded-lg px-3 py-1.5 hover:border-white/40 whitespace-nowrap">↻ Refresh</button>
              </div>
              {pathsErr && <p className="text-red-400 text-sm">{pathsErr}</p>}
              {!paths && !pathsErr && <p className="text-slate-500 text-sm">Working out the paths…</p>}
              {paths && paths.customer && (
                <div className="bg-green-500/10 border border-green-500/30 rounded-xl p-4"><p className="text-white text-sm">{paths.summary}</p>
                  <p className="text-slate-400 text-xs mt-1">{paths.note}</p></div>
              )}
              {paths && !paths.customer && (
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
                            {st.action === paths.best && <span className="text-[10px] text-green-400 border border-green-500/40 rounded-full px-2 py-0.5 h-fit">recommended</span>}
                          </div>
                          <p className="text-slate-300 text-xs mt-1">{p1(st.p_buy_step)} chance to buy in 14 days
                            {st.action !== 'none' ? ` · ${pts(st.uplift)} · ${inr(st.extra_profit)} vs doing nothing` : ''}</p>
                          <p className="text-slate-600 text-[11px]">reactions: {st.reactions?.length ? `${st.evidence.basis} (${st.evidence.decisions} decisions)` : `not enough history yet (${st.evidence.decisions} decisions; ${paths.history?.min_history} needed)`}</p>
                        </button>
                      ))}
                    </div>
                  </div>
                  {(() => {
                    const st = paths.steps.find(x => x.action === pick) || paths.steps[0]
                    if (!st) return null
                    return (
                      <div>
                        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
                          <p className="text-slate-400 text-xs uppercase tracking-wide font-semibold">If the team chooses “{st.label}”</p>
                          {st.action !== 'none' && !paths.lead.control_group && (
                            <button onClick={() => act(st.action)} disabled={!!busy} className="btn text-xs py-1.5 px-3 disabled:opacity-50">
                              {busy === st.action ? 'Working…' : `▶ Do it now: ${DO_LABEL[st.action] || st.label}`}</button>
                          )}
                        </div>
                        {st.reactions?.length ? <PathTree lead={paths.lead} step={st} />
                          : <p className="text-slate-400 text-sm">Not enough history yet to say how learners react to this step
                              ({st.evidence.decisions} past decisions; {paths.history?.min_history} needed). The chance to buy above still comes from the models.</p>}
                      </div>
                    )
                  })()}
                  {Object.keys(paths.blocked || {}).length > 0 && (
                    <p className="text-slate-500 text-xs">Not possible now: {Object.entries(paths.blocked).map(([a, why]) => `${a.replaceAll('_', ' ')} (${why})`).join(' · ')}</p>
                  )}
                  <p className="text-slate-500 text-[11px]">{paths.note} History used: {paths.history?.decisions?.toLocaleString?.() ?? 0} decisions
                    ({paths.history?.stage_decisions ?? 0} for {stageLabel(paths.lead.stage)} leads).</p>
                </>
              )}
            </div>
          )}

          {tab === 'explain' && (
            <div className="card p-6">
              <h3 className="font-display font-semibold text-white mb-1">Why this score?</h3>
              <p className="text-slate-500 text-xs mb-4">Each line shows how many points the score would change without that signal, worked out by the current
                model just now. The score is the chance this person buys within 14 days if we do nothing now.{explain?.model_version ? ` Model: ${explain.model_version}.` : ''}</p>
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
