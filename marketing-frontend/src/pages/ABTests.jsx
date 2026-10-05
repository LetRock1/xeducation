import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'
import { createAbTest, getAbTests, sendAbTest, getAbTestResults, planAbTest, applyAbWinner, deleteAbTest,
  getAdoptions, checkAdoptions, revertAdoption } from '../utils/api'

const TIP = { background: '#0B1426', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 12, color: '#e2e8f0' }
const TIERS = ['All leads', 'Target Immediately', 'Nurture via Email/WhatsApp', 'Marketing Campaign', 'Low Priority']
const KEYS = ['A', 'B', 'C']
const ARM_COLOR = { control: '#64748b', A: '#38BDF8', B: '#f97316', C: '#a78bfa' }
const pct = (x, d = 1) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`)
const pts = (x, d = 1) => (x == null ? '—' : `${x >= 0 ? '+' : ''}${(x * 100).toFixed(d)} pts`)
const money = x => (x == null ? '—' : `₹${Math.round(x).toLocaleString('en-IN')}`)
const day = s => (s ? String(s).slice(0, 10) : '—')
const short = t => (t === 'Nurture via Email/WhatsApp' ? 'Nurture' : t === 'Marketing Campaign' ? 'Campaign' : t)
const blank = k => ({ label: `Variant ${k}`, subject: '', body: '', offer_pct: 0 })

const STATE = {
  draft: ['Draft', 'text-yellow-400 bg-yellow-500/10 border-yellow-500/30'],
  sending: ['Sending…', 'text-sky-accent bg-sky-500/10 border-sky-500/30'],
  running: ['Running', 'text-sky-accent bg-sky-500/10 border-sky-500/30'],
  completed: ['Final', 'text-slate-300 bg-white/5 border-white/15'],
}
const VERDICT = {
  winner: ['Winner', 'text-green-400 bg-green-500/10 border-green-500/30'],
  loser: ['Variant worse', 'text-red-400 bg-red-500/10 border-red-500/30'],
  no_difference: ['No clear difference', 'text-slate-300 bg-white/5 border-white/15'],
  running: ['Not final yet', 'text-slate-400 bg-white/5 border-white/10'],
  broken: ['Split broken', 'text-red-400 bg-red-500/10 border-red-500/30'],
  waiting: ['Waiting', 'text-slate-400 bg-white/5 border-white/10'],
  error: ['Error', 'text-red-400 bg-red-500/10 border-red-500/30'],
}
function Chip({ map, k, extra }) {
  const [text, cls] = map[k] || [k || '—', 'text-slate-400 bg-white/5 border-white/10']
  return <span className={`text-[11px] px-2 py-0.5 rounded-full border whitespace-nowrap ${cls}`}>{text}{extra}</span>
}

/* Lift of each variant vs the reference with its 95% interval (a "forest plot"). */
function LiftChart({ comparisons, refLabel, what }) {
  const vals = comparisons.flatMap(c => [c.lift, ...(c.lift_ci || [])]).filter(v => v != null)
  const m = Math.max(0.02, ...vals.map(Math.abs)) * 1.15
  const W = 640, padL = 96, padR = 170, rowH = 46, H = comparisons.length * rowH + 40
  const x = v => padL + ((v + m) / (2 * m)) * (W - padL - padR)
  const ticks = [-m, -m / 2, 0, m / 2, m]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img" aria-label={`Lift in ${what} versus ${refLabel}`}>
      {ticks.map((t, i) => (
        <g key={i}>
          <line x1={x(t)} x2={x(t)} y1={8} y2={H - 26} stroke={t === 0 ? '#94a3b8' : 'rgba(255,255,255,0.06)'} strokeDasharray={t === 0 ? '0' : '3 3'} />
          <text x={x(t)} y={H - 10} fill="#64748b" fontSize="11" textAnchor="middle">{pts(t, Math.abs(m) < 0.05 ? 1 : 0)}</text>
        </g>
      ))}
      <text x={x(0) + 4} y={16} fill="#94a3b8" fontSize="10">= {refLabel}</text>
      {comparisons.map((c, i) => {
        const y = 30 + i * rowH
        const [lo, hi] = c.lift_ci || [null, null]
        const color = c.significant ? (c.lift > 0 ? '#22c55e' : '#ef4444') : '#cbd5e1'
        return (
          <g key={c.variant}>
            <text x={8} y={y + 4} fill={ARM_COLOR[c.variant] || '#e2e8f0'} fontSize="12" fontWeight="600">Variant {c.variant}</text>
            {lo != null && hi != null && <line x1={x(lo)} x2={x(hi)} y1={y} y2={y} stroke={color} strokeWidth="3" strokeLinecap="round" />}
            <circle cx={x(c.lift)} cy={y} r="6" fill={color} />
            <text x={W - padR + 10} y={y - 2} fill="#e2e8f0" fontSize="12" fontWeight="600">{pts(c.lift)}</text>
            <text x={W - padR + 10} y={y + 13} fill="#94a3b8" fontSize="10">95%: {pts(lo)} to {pts(hi)}</text>
          </g>
        )
      })}
    </svg>
  )
}

function Plan({ plan, metric }) {
  if (!plan) return null
  const what = metric === 'click' ? 'click' : 'purchase'
  return (
    <div className={`rounded-xl border p-3 text-xs ${plan.enough ? 'border-green-500/30 bg-green-500/5 text-slate-300' : 'border-amber-500/40 bg-amber-500/5 text-slate-300'}`}>
      <p><span className="text-white font-semibold">{plan.audience.toLocaleString()}</span> people in this audience →
        about <span className="text-white font-semibold">{plan.per_arm_available.toLocaleString()}</span> in the smallest arm.</p>
      <p className="mt-1">To detect a {pts(plan.mde, 0)} lift on a typical {what} rate of {pct(plan.baseline_rate)}, each arm needs
        {' '}<span className="text-white font-semibold">{plan.planned_per_arm.toLocaleString()}</span> people (95% confidence, 80% power).</p>
      {plan.enough
        ? <p className="mt-1 text-green-400">Enough people — this test can find the lift you are looking for.</p>
        : <p className="mt-1 text-amber-300">Not enough people: this test can only detect lifts of about {pts(plan.detectable_lift)} or more. Use fewer variants, a smaller control group or a bigger audience.</p>}
    </div>
  )
}

function Results({ data, onApply, applying }) {
  const { test, results: r } = data
  const [dim, setDim] = useState('tier')
  if (!r) return null
  const arms = r.arms || []
  const comps = r.comparisons || []
  const refArm = arms.find(a => a.arm === r.reference)
  const refLabel = r.reference === 'control' ? 'sending nothing' : `variant ${r.reference}`
  const what = r.metric === 'bought' ? 'purchases' : 'clicks'
  const v = r.verdict || {}
  const segs = (r.segments || {})[dim] || []
  const armKeys = arms.map(a => a.arm)
  const label = k => (k === 'control' ? 'Control' : `Variant ${k}`)
  const winner = v.status === 'winner' ? v.winner : null
  return (
    <div className="card p-6 mt-6">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h2 className="font-display text-xl font-bold text-white">{test.name}</h2>
          <p className="text-slate-400 text-xs mt-1">{short(test.tier)} · {r.metric === 'bought' ? `purchases within ${r.window_days} days` : 'clicks'}
            {' '}· sent {day(test.started_at || test.sent_at)}{test.simulated ? ' · simulated history' : ''}</p>
          {test.hypothesis && <p className="text-slate-300 text-sm mt-2"><span className="text-slate-500">Hypothesis:</span> {test.hypothesis}</p>}
        </div>
        <Chip map={STATE} k={test.state} extra={test.state === 'running' ? ` · day ${Math.min(r.days_since_start, r.window_days)}/${r.window_days}` : ''} />
      </div>

      <div className={`rounded-xl border p-4 mb-5 ${v.status === 'winner' ? 'border-green-500/40 bg-green-500/5' : v.status === 'broken' || v.status === 'loser' ? 'border-red-500/40 bg-red-500/5' : 'border-white/10 bg-white/5'}`}>
        <p className="text-white font-semibold">{v.headline}</p>
        <p className="text-slate-300 text-sm mt-1">{v.detail}</p>
        {!r.final && <p className="text-slate-500 text-xs mt-1">Fixed horizon: numbers before day {r.window_days} are shown for interest only — the verdict is made once, at the end (no peeking).</p>}
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mb-6">
        <div>
          <h3 className="text-white font-semibold text-sm mb-2">Each arm</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead><tr className="text-slate-500 text-left"><th className="py-1">Arm</th><th>People</th><th>{r.metric === 'bought' ? 'Bought' : 'Clicked'}</th><th>Rate (95%)</th><th>Revenue / person</th><th>Profit / person</th></tr></thead>
              <tbody>{arms.map(a => (
                <tr key={a.arm} className={`border-t border-white/5 ${a.arm === winner ? 'text-white' : 'text-slate-300'}`}>
                  <td className="py-1.5"><span className="inline-block w-2.5 h-2.5 rounded-sm mr-1.5 align-middle" style={{ background: ARM_COLOR[a.arm] }} />{a.label}{a.arm === winner ? ' 🏆' : ''}</td>
                  <td>{a.n.toLocaleString()}</td>
                  <td>{(r.metric === 'bought' ? a.purchases : a.clicks).toLocaleString()}</td>
                  <td>{pct(a.rate)} <span className="text-slate-500">({pct(a.rate_ci?.[0])}–{pct(a.rate_ci?.[1])})</span></td>
                  <td>{money(a.revenue_per_person)}</td>
                  <td>{money(a.profit_per_person)}</td>
                </tr>))}
              </tbody>
            </table>
          </div>
          <p className="text-slate-500 text-[11px] mt-2">Profit = revenue − email cost; coupon discounts are already taken off the price paid.
            {r.reference === 'control' ? ' The control group got no email: the difference to it is what the email caused.' : ' Click tests compare variants with each other (people who get no email cannot click).'}</p>
        </div>
        <div>
          <h3 className="text-white font-semibold text-sm mb-1">Lift vs {refLabel}</h3>
          <p className="text-slate-500 text-[11px] mb-2">Dot = measured lift in {what}; line = 95% interval{r.bonferroni_comparisons > 1 ? ` (Bonferroni-adjusted for ${r.bonferroni_comparisons} variants)` : ''}. Green = clearly better, red = clearly worse, grey = could be chance.</p>
          {comps.length ? <LiftChart comparisons={comps} refLabel={refLabel} what={what} /> : <p className="text-slate-400 text-sm">No comparison yet.</p>}
          {refArm && comps.length > 0 && (
            <table className="w-full text-[11px] mt-2">
              <thead><tr className="text-slate-500 text-left"><th className="py-1">Variant</th><th>Relative</th><th>p (adjusted)</th><th>Revenue lift / person</th></tr></thead>
              <tbody>{comps.map(c => (
                <tr key={c.variant} className="border-t border-white/5 text-slate-300">
                  <td className="py-1">{c.variant}</td>
                  <td>{c.relative_lift == null ? '—' : `${c.relative_lift >= 0 ? '+' : ''}${(c.relative_lift * 100).toFixed(0)}%`}</td>
                  <td>{c.p_adjusted == null ? '—' : c.p_adjusted < 0.001 ? '< 0.001' : c.p_adjusted.toFixed(3)}</td>
                  <td>{money(c.revenue_lift_per_person)} <span className="text-slate-500">({money(c.revenue_lift_ci?.[0])} to {money(c.revenue_lift_ci?.[1])})</span></td>
                </tr>))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mb-6">
        <div>
          <h3 className="text-white font-semibold text-sm mb-1">Over the {r.window_days} days</h3>
          <p className="text-slate-500 text-[11px] mb-2">Share of each arm that had {r.metric === 'bought' ? 'bought' : 'clicked'} by each day after the send.</p>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={r.curve || []} margin={{ top: 5, right: 16, left: -16, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="day" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} unit="%" />
              <Tooltip contentStyle={TIP} formatter={(val, name) => [`${val}%`, label(name)]} labelFormatter={d => `Day ${d}`} />
              <Legend formatter={label} wrapperStyle={{ fontSize: 11, color: '#94a3b8' }} />
              {armKeys.map(k => <Line key={k} type="monotone" dataKey={k} stroke={ARM_COLOR[k]} strokeWidth={k === 'control' ? 1.5 : 2} strokeDasharray={k === 'control' ? '5 4' : '0'} dot={false} />)}
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div>
          <h3 className="text-white font-semibold text-sm mb-2">Is the test itself sound?</h3>
          <ul className="text-xs text-slate-300 space-y-2">
            <li>{r.srm_problem ? '❌' : '✅'} <span className="font-semibold">Split check</span> — arm sizes {r.srm_problem ? 'differ from the plan far more than chance allows' : 'match the planned shares'}
              {r.srm_p != null ? ` (p = ${r.srm_p < 0.001 ? '< 0.001' : r.srm_p.toFixed(3)})` : ''}.</li>
            <li>{r.smallest_arm >= r.planned_per_arm ? '✅' : '⚠️'} <span className="font-semibold">Size</span> — smallest arm {r.smallest_arm?.toLocaleString()} people;
              {' '}{r.planned_per_arm?.toLocaleString()} needed for the planned lift. Smallest lift it can reliably detect: {pts(r.detectable_lift)}.</li>
            <li>{r.final ? '✅' : '⏳'} <span className="font-semibold">Outcome window</span> — {r.final ? `complete (${r.window_days} days for everyone)` : `day ${Math.min(r.days_since_start, r.window_days)} of ${r.window_days}`}.</li>
            <li>🔁 <span className="font-semibold">Feeds the learning loop</span> — every assignment, including the no-email group, tells the <Link to="/learning" className="text-sky-accent hover:underline">learning loop</Link> what the CRM did, so it does not mistake an e-mail's effect for lead quality.</li>
          </ul>
          {winner && (
            <div className="mt-4">
              <button onClick={() => onApply(test.id, winner, test.tier)} disabled={applying} className="btn text-sm disabled:opacity-60">
                {applying ? 'Creating…' : `Use variant ${winner} for ${short(test.tier)} (campaign draft)`}
              </button>
              {test.applied_campaign_id && <p className="text-slate-500 text-[11px] mt-1">Already turned into campaign draft #{test.applied_campaign_id} — see <Link to="/campaigns" className="text-sky-accent hover:underline">Campaigns</Link>.</p>}
            </div>
          )}
        </div>
      </div>

      <div>
        <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
          <h3 className="text-white font-semibold text-sm">Who it worked for <span className="text-slate-500 font-normal">(exploratory)</span></h3>
          <div className="flex gap-1">
            {['tier', 'occupation', 'device', 'source'].map(d => (
              <button key={d} onClick={() => setDim(d)} className={`text-xs px-3 py-1 rounded-lg border ${dim === d ? 'border-ember text-white bg-ember/10' : 'border-white/10 text-slate-400 hover:text-white'}`}>{d}</button>
            ))}
          </div>
        </div>
        <p className="text-slate-500 text-[11px] mb-2">Rate in each arm per segment; a variant is marked best only where its 95% interval vs {refLabel} is above zero and both groups have enough people. Segment results are for ideas — confirm them with a new test.</p>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="text-slate-500 text-left"><th className="py-1">{dim}</th>
              {armKeys.map(k => <th key={k}>{label(k)}</th>)}<th>Best</th><th /></tr></thead>
            <tbody>{segs.map(s => (
              <tr key={s.value} className={`border-t border-white/5 ${s.enough ? 'text-slate-300' : 'text-slate-500'}`}>
                <td className="py-1.5">{s.value}{!s.enough && <span className="block text-[10px]">small group</span>}</td>
                {armKeys.map(k => {
                  const a = s.arms[k] || {}
                  return <td key={k}>{pct(a.rate)} <span className="text-slate-500">n={a.n ?? 0}</span>
                    {a.lift != null && <span className={`block text-[10px] ${a.lift_ci?.[0] > 0 ? 'text-green-400' : a.lift_ci?.[1] < 0 ? 'text-red-400' : 'text-slate-500'}`}>{pts(a.lift)}</span>}</td>
                })}
                <td>{s.best ? <span className="text-green-400 font-semibold">Variant {s.best}</span> : '—'}</td>
                <td>{dim === 'tier' && s.best && TIERS.includes(s.value) && (
                  <button onClick={() => onApply(test.id, s.best, s.value)} disabled={applying} className="text-[11px] text-sky-accent hover:underline disabled:opacity-50">Use for {short(s.value)}</button>
                )}</td>
              </tr>))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

const ADOPT = {
  active: ['Checking', 'text-sky-accent bg-sky-500/10 border-sky-500/30'],
  confirmed: ['Still winning', 'text-green-400 bg-green-500/10 border-green-500/30'],
  reverted: ['Switched back', 'text-red-400 bg-red-500/10 border-red-500/30'],
  superseded: ['Replaced', 'text-slate-400 bg-white/5 border-white/10'],
}

/* Winners the CRM adopted by itself, and its running check against the old email. */
function Adopted({ data, onCheck, onRevert, busy }) {
  if (!data) return null
  const rows = data.adoptions || []
  return (
    <div className="card p-6 mt-6">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-1">
        <div>
          <h2 className="font-display text-lg font-bold text-white">Adopted winners</h2>
          <p className="text-slate-400 text-xs mt-1 max-w-3xl">When a test is final and an email without a discount clearly won, the CRM makes it the standard
            information email for that audience — {data.auto_adopt ? 'automatically' : 'when switched on in crm_settings.json'}.
            {' '}{Math.round((data.check_share || 0.1) * 100)}% of the audience keeps the old email, so it keeps checking that the winner still wins, and switches back by itself if not.</p>
        </div>
        <button onClick={onCheck} disabled={busy} className="text-xs border border-white/15 text-slate-200 rounded-lg px-3 py-1.5 hover:border-white/40 disabled:opacity-50">{busy ? 'Checking…' : 'Check now'}</button>
      </div>
      {!rows.length ? <p className="text-slate-500 text-sm mt-3">Nothing adopted yet — it happens when a final test has a clear winner without a discount.</p> : (
        <div className="space-y-3 mt-4">
          {rows.map(a => {
            const c = a.check || {}
            const arms = c.arms || []
            return (
              <div key={a.id} className="rounded-xl border border-white/10 bg-white/5 p-4">
                <div className="flex flex-wrap items-start gap-2">
                  <p className="text-white font-semibold text-sm flex-1">“{a.variant_label}” → standard information email for {a.audience}</p>
                  <Chip map={ADOPT} k={a.status} />
                </div>
                <p className="text-slate-400 text-[11px] mt-1">From the test “{(a.test_name || '').replace('(simulated) ', '')}”{a.simulated ? ' (simulated)' : ''} ·
                  won by {pts(a.test_lift)} {a.metric === 'click' ? 'clicks' : 'purchases'} · adopted {day(a.adopted_at)}{a.decided_at ? ` · ${a.status} ${day(a.decided_at)}` : ''}</p>
                <p className="text-slate-300 text-xs mt-2"><span className="text-slate-500">Subject:</span> {a.subject}</p>
                {arms.length > 0 && (
                  <div className="grid sm:grid-cols-2 gap-2 mt-3">
                    {arms.map(r => (
                      <div key={r.arm} className="bg-[#0B1426] rounded-lg px-3 py-2 border border-white/10">
                        <p className="text-slate-400 text-[11px]">{r.label}</p>
                        <p className="text-white text-sm font-semibold">{pct(r.rate)} <span className="text-slate-500 text-[11px] font-normal">{a.metric === 'click' ? 'clicked' : 'bought'} · {r.n?.toLocaleString()} people</span></p>
                      </div>
                    ))}
                  </div>
                )}
                {(c.why || a.reason) && <p className="text-slate-300 text-xs mt-2">{a.status === 'active' || a.status === 'confirmed' ? c.why : (a.reason || c.why)}</p>}
                {(a.status === 'active' || a.status === 'confirmed') && (
                  <button onClick={() => onRevert(a.id)} className="text-[11px] text-slate-500 hover:text-red-400 mt-2">Switch back to the old email</button>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function ABTests() {
  const [tests, setTests] = useState([])
  const [form, setForm] = useState({ name: '', hypothesis: '', tier: 'All leads', metric: 'purchase', control_share: 0.2, mde: 0.05 })
  const [variants, setVariants] = useState([blank('A'), blank('B')])
  const [plan, setPlan] = useState(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [openId, setOpenId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [applying, setApplying] = useState(false)
  const [sendingId, setSendingId] = useState(null)
  const [adopted, setAdopted] = useState(null)
  const [checking, setChecking] = useState(false)
  const timer = useRef(null)
  const location = useLocation()

  const load = () => {
    getAbTests().then(r => setTests(r.data.ab_tests || [])).catch(() => {})
    getAdoptions().then(r => setAdopted(r.data)).catch(() => {})
  }
  useEffect(() => { load() }, [])

  // a test drafted by the Copilot arrives here pre-filled; a person reviews it and creates it
  useEffect(() => {
    const d = location.state?.draft
    if (!d) return
    setForm({ name: d.name || '', hypothesis: d.hypothesis || '', tier: d.tier || 'All leads', metric: d.metric || 'purchase',
      control_share: d.control_share ?? 0.2, mde: d.mde ?? 0.05 })
    if (d.variants?.length) setVariants(d.variants.map((v, i) => ({ label: v.label || `Variant ${KEYS[i]}`, subject: v.subject || '', body: v.body || '', offer_pct: v.offer_pct || 0 })))
    setMsg({ ok: true, text: 'Draft from the Copilot — review it, change anything, then press “Create test”. Nothing has been created or sent yet.' })
  }, [location.state])

  async function checkNow() {
    setChecking(true)
    try { const r = await checkAdoptions(); setAdopted(a => ({ ...(a || {}), adoptions: r.data.adoptions })); load()
      setMsg({ ok: true, text: r.data.changes?.length ? `${r.data.changes.length} change(s): ${r.data.changes.map(c => c.adopted ? `adopted “${c.variant}”` : `switched back (${c.test})`).join('; ')}` : 'Checked — nothing changed.' }) }
    catch (e) { setMsg({ ok: false, text: e.response?.data?.detail || 'Could not run the check.' }) }
    finally { setChecking(false) }
  }
  async function revert(id) {
    if (!window.confirm('Switch back to the old standard email for this audience?')) return
    try { await revertAdoption(id); load() } catch (e) { setMsg({ ok: false, text: e.response?.data?.detail || 'Could not switch back.' }) }
  }

  const effectiveControl = form.metric === 'click' ? 0 : form.control_share
  useEffect(() => {
    clearTimeout(timer.current)
    timer.current = setTimeout(() => {
      planAbTest({ tier: form.tier, metric: form.metric, variants: variants.length, control_share: effectiveControl, mde: form.mde })
        .then(r => setPlan(r.data)).catch(() => setPlan(null))
    }, 300)
    return () => clearTimeout(timer.current)
  }, [form.tier, form.metric, variants.length, effectiveControl, form.mde])

  async function open(id) {
    setOpenId(id); setDetail(null)
    try { const r = await getAbTestResults(id); setDetail(r.data) } catch (e) { setMsg({ ok: false, text: e.response?.data?.detail || 'Could not load results.' }) }
  }

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const setVar = (i, k, v) => setVariants(vs => vs.map((x, j) => (j === i ? { ...x, [k]: v } : x)))

  async function submit(e) {
    e.preventDefault(); setBusy(true); setMsg(null)
    try {
      const r = await createAbTest({ ...form, control_share: effectiveControl,
        variants: variants.map(v => ({ ...v, offer_pct: Number(v.offer_pct) || 0 })) })
      setMsg({ ok: true, text: r.data.message + (r.data.warning ? ` ${r.data.warning}` : ' Send it from the list when ready.') })
      setForm(f => ({ ...f, name: '', hypothesis: '' }))
      setVariants([blank('A'), blank('B')])
      load()
    } catch (err) {
      setMsg({ ok: false, text: err.response?.data?.detail || 'Could not create the test.' })
    } finally { setBusy(false) }
  }

  async function send(id) {
    if (!window.confirm('Send this test now? Every person in the audience is assigned to an arm and the emails go out.')) return
    setSendingId(id)
    try { const r = await sendAbTest(id); setMsg({ ok: true, text: r.data.message }); load(); if (openId === id) open(id) }
    catch (err) { setMsg({ ok: false, text: err.response?.data?.detail || 'Could not send.' }) }
    finally { setSendingId(null) }
  }

  async function remove(id) {
    if (!window.confirm('Delete this draft?')) return
    try { await deleteAbTest(id); load(); if (openId === id) { setOpenId(null); setDetail(null) } }
    catch (err) { setMsg({ ok: false, text: err.response?.data?.detail || 'Could not delete.' }) }
  }

  async function apply(id, variant, tier) {
    setApplying(true)
    try { const r = await applyAbWinner(id, { variant, tier }); setMsg({ ok: true, text: r.data.message }); load(); open(id) }
    catch (err) { setMsg({ ok: false, text: err.response?.data?.detail || 'Could not create the campaign.' }) }
    finally { setApplying(false) }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-display text-3xl font-extrabold text-white">A/B tests</h1>
        <p className="text-slate-400 text-sm mt-1 max-w-3xl">Every purchase test keeps a random <span className="text-white">no-email control group</span>, so the result is the
          purchases an email <span className="text-white">caused</span> — not just which variant won. People are split by a fixed hash, the size needed is planned up front,
          and the verdict is made once, when the 14-day outcome window has passed, with 95% intervals.</p>
      </div>

      {msg && <p className={`text-sm px-3 py-2 rounded-xl border mb-4 ${msg.ok ? 'text-green-400 bg-green-900/20 border-green-800/30' : 'text-red-400 bg-red-900/20 border-red-800/30'}`}>{msg.text}</p>}

      <div className="grid lg:grid-cols-5 gap-6">
        {/* create */}
        <form onSubmit={submit} className="card p-6 lg:col-span-3 space-y-4">
          <h2 className="font-display text-lg font-bold text-white">New test</h2>
          <div className="grid sm:grid-cols-2 gap-3">
            <div><label className="lbl">Name *</label>
              <input required value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Course pick vs newsletter" className="inp" /></div>
            <div><label className="lbl">Audience *</label>
              <select value={form.tier} onChange={e => set('tier', e.target.value)} className="inp">{TIERS.map(t => <option key={t}>{t}</option>)}</select></div>
          </div>
          <div><label className="lbl">Hypothesis</label>
            <input value={form.hypothesis} onChange={e => set('hypothesis', e.target.value)} placeholder="e.g. Recommending one course gets more purchases than a general newsletter" className="inp" /></div>
          <div className="grid sm:grid-cols-3 gap-3">
            <div><label className="lbl">Success measure</label>
              <select value={form.metric} onChange={e => set('metric', e.target.value)} className="inp">
                <option value="purchase">Purchases (14 days)</option><option value="click">Clicks</option></select></div>
            <div><label className="lbl">Control group (no email)</label>
              <select value={effectiveControl} disabled={form.metric === 'click'} onChange={e => set('control_share', Number(e.target.value))} className="inp disabled:opacity-50">
                {[0, 0.1, 0.2, 0.3].map(s => <option key={s} value={s}>{s ? `${s * 100}%` : 'none'}</option>)}</select></div>
            <div><label className="lbl">Smallest lift worth finding</label>
              <select value={form.mde} onChange={e => set('mde', Number(e.target.value))} className="inp">
                {[0.02, 0.03, 0.05, 0.1].map(s => <option key={s} value={s}>{`+${s * 100} pts`}</option>)}</select></div>
          </div>
          {form.metric === 'click' && <p className="text-slate-500 text-[11px] -mt-2">Click tests have no control group — people who get no email can't click — so variants are compared with each other.</p>}

          <div className="space-y-3">
            {variants.map((v, i) => (
              <div key={i} className="rounded-xl border border-white/10 p-3" style={{ borderLeft: `3px solid ${ARM_COLOR[KEYS[i]]}` }}>
                <div className="flex items-center gap-2 mb-2">
                  <input value={v.label} onChange={e => setVar(i, 'label', e.target.value)} className="inp !py-1.5 text-sm font-semibold flex-1" />
                  <select value={v.offer_pct} onChange={e => setVar(i, 'offer_pct', Number(e.target.value))} className="inp !py-1.5 !w-auto text-xs" title="Adds a personal coupon to this variant">
                    {[0, 10, 15, 20].map(o => <option key={o} value={o}>{o ? `${o}% coupon` : 'no coupon'}</option>)}</select>
                  {variants.length > 2 && <button type="button" onClick={() => setVariants(vs => vs.filter((_, j) => j !== i).map((x, j) => (/^Variant [ABC]$/.test(x.label) ? { ...x, label: `Variant ${KEYS[j]}` } : x)))} className="text-slate-500 hover:text-red-400 text-xs px-2">Remove</button>}
                </div>
                <input required value={v.subject} onChange={e => setVar(i, 'subject', e.target.value)} placeholder="Subject — {first_name} and {course} are filled in" className="inp mb-2" />
                <textarea required value={v.body} onChange={e => setVar(i, 'body', e.target.value)} rows={3} placeholder="Email text" className="inp text-xs" />
              </div>
            ))}
            {variants.length < 3 && <button type="button" onClick={() => setVariants(vs => [...vs, blank(KEYS[vs.length])])} className="text-sm text-sky-accent hover:underline">+ Add variant {KEYS[variants.length]}</button>}
          </div>

          <Plan plan={plan} metric={form.metric} />
          <button type="submit" disabled={busy} className="w-full btn">{busy ? 'Creating…' : 'Create test (draft)'}</button>
        </form>

        {/* list */}
        <div className="card p-6 lg:col-span-2">
          <h2 className="font-display text-lg font-bold text-white mb-4">Tests <span className="text-slate-500 font-body font-normal text-sm">({tests.length})</span></h2>
          {!tests.length ? <p className="text-slate-500 text-sm text-center py-10">No tests yet.</p> : (
            <div className="space-y-3 max-h-[760px] overflow-y-auto pr-1">
              {tests.map(t => (
                <div key={t.id} className={`rounded-xl border p-4 ${openId === t.id ? 'border-ember/50 bg-ember/5' : 'border-white/10 bg-white/5'}`}>
                  <div className="flex items-start gap-2">
                    <p className="font-semibold text-white text-sm flex-1">{t.name}</p>
                    <Chip map={STATE} k={t.state} />
                  </div>
                  <p className="text-slate-400 text-[11px] mt-1">{short(t.tier)} · {t.metric === 'click' ? 'clicks' : 'purchases'} · {t.variants?.length || 2} variants
                    {t.control_share ? ` + ${Math.round(t.control_share * 100)}% control` : ''}{t.people ? ` · ${t.people.toLocaleString()} people` : ''}{t.simulated ? ' · simulated' : ''}</p>
                  {t.verdict && t.state !== 'draft' && (
                    <div className="mt-2 flex items-start gap-2">
                      <Chip map={VERDICT} k={t.verdict.status} />
                      <p className="text-slate-300 text-[11px] leading-snug">{t.verdict.headline}</p>
                    </div>
                  )}
                  {t.adoption && <p className="text-[11px] text-green-400 mt-1">Adopted as the standard email ({(ADOPT[t.adoption.status] || [t.adoption.status])[0].toLowerCase()})</p>}
                  <div className="flex gap-2 mt-3">
                    {t.state === 'draft' ? (
                      <>
                        <button onClick={() => send(t.id)} disabled={sendingId === t.id} className="btn text-xs py-1.5 flex-1 disabled:opacity-60">{sendingId === t.id ? 'Sending…' : 'Send now'}</button>
                        <button onClick={() => open(t.id)} className="text-xs border border-white/15 text-slate-300 rounded-lg px-3 hover:border-white/40">Plan</button>
                        <button onClick={() => remove(t.id)} className="text-xs text-slate-500 hover:text-red-400 px-2">Delete</button>
                      </>
                    ) : t.state === 'sending' ? <p className="text-slate-500 text-xs">Sending in progress — refresh in a moment.</p> : (
                      <button onClick={() => open(t.id)} className="text-xs border border-white/15 text-slate-200 rounded-lg px-3 py-1.5 hover:border-white/40">{openId === t.id ? 'Refresh results' : 'Open results'}</button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {openId && !detail && <div className="flex items-center justify-center h-32"><div className="w-7 h-7 border-4 border-ember border-t-transparent rounded-full animate-spin" /></div>}
      {detail && detail.results && <Results data={detail} onApply={apply} applying={applying} />}
      <Adopted data={adopted} onCheck={checkNow} onRevert={revert} busy={checking} />
      {detail && !detail.results && detail.plan && (
        <div className="card p-6 mt-6">
          <h2 className="font-display text-lg font-bold text-white mb-1">{detail.test.name} — draft</h2>
          <p className="text-slate-400 text-xs mb-3">{short(detail.test.tier)} · {(detail.test.variants || []).map(v => v.label || v.key).join(' vs ')}{detail.test.control_share ? ` vs control (${Math.round(detail.test.control_share * 100)}%)` : ''}</p>
          <Plan plan={detail.plan} metric={detail.test.metric} />
        </div>
      )}
    </div>
  )
}
