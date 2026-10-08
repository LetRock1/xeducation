import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, LineChart, Line, Legend, CartesianGrid, Cell, ReferenceLine } from 'recharts'
import { getLearning, runLearning } from '../utils/api'

const TIP = { background:'#0B1426', border:'1px solid rgba(255,255,255,0.1)', borderRadius:12, color:'#e2e8f0' }
const pct = (x, d = 0) => (x == null ? '—' : `${(x * 100).toFixed(d)}%`)
const num = x => (x == null ? '—' : Number(x).toLocaleString())
const auc = x => (x == null ? '—' : Number(x).toFixed(3))
const ll = x => (x == null ? '—' : Number(x).toFixed(4))
const day = s => (s ? String(s).slice(0, 10) : '—')
const DECISION = {
  swapped: { text: 'swapped', cls: 'text-green-400 bg-green-500/10 border-green-500/30' },
  kept: { text: 'kept', cls: 'text-sky-accent bg-sky-500/10 border-sky-500/30' },
  not_enough_data: { text: 'not enough data', cls: 'text-slate-400 bg-white/5 border-white/10' },
  error: { text: 'error', cls: 'text-red-400 bg-red-500/10 border-red-500/30' },
}
function Chip({ d }) {
  const c = DECISION[d] || { text: d || '—', cls: 'text-slate-400 bg-white/5 border-white/10' }
  return <span className={`text-[11px] px-2 py-0.5 rounded-full border ${c.cls}`}>{c.text}</span>
}

function Step({ icon, title, value, sub, highlight }) {
  return (
    <div className={`card p-4 flex-1 min-w-[150px] ${highlight ? 'border-ember/50 bg-ember/5' : ''}`}>
      <p className="text-lg leading-none mb-2">{icon}</p>
      <p className="text-slate-400 text-[11px] uppercase tracking-wide font-semibold">{title}</p>
      <p className="font-display text-2xl font-extrabold text-white mt-1">{value}</p>
      <p className="text-slate-500 text-[11px] mt-1 leading-snug">{sub}</p>
    </div>
  )
}

export default function Learning() {
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const loading = useRef(false)

  function load() {
    if (loading.current) return
    loading.current = true
    getLearning().then(r => { setData(r.data); setErr('') })
      .catch(e => setErr(e.response?.data?.detail || 'Could not load the learning loop.'))
      .finally(() => { loading.current = false })
  }
  useEffect(() => { load(); const t = setInterval(load, 5000); return () => clearInterval(t) }, [])

  async function retrain(dryRun) {
    setBusy(true); setResult(null)
    try {
      const r = await runLearning(dryRun)
      setResult({ ok: true, ...r.data })
      load()
    } catch (e) {
      setResult({ ok: false, note: e.response?.data?.detail || 'The learning run failed.' })
    } finally { setBusy(false) }
  }

  if (!data) return err ? <p className="text-red-400 text-center mt-20">{err}</p>
    : <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin" /></div>

  const c = data.counts
  const runs = data.runs || []
  const last = runs[0]
  const st = data.status
  const lat = st?.latency || {}
  const lm = data.lead_model || {}
  const learned = (lm.learned_signals || []).filter(s => Math.abs(s.points) >= 0.1).sort((a, b) => b.points - a.points)
  const byDay = new Map()                      // one point per day (the latest run of that day)
  for (const r of [...runs].reverse()) {
    const c = r.learned?.control || {}
    const p = c.predicted || {}
    if (c.actual == null) continue
    byDay.set(day(r.as_of), { date: day(r.as_of), actual: +(c.actual * 100).toFixed(1),
      ours: p.challenger != null ? +(p.challenger * 100).toFixed(1) : null, naive: p.naive != null ? +(p.naive * 100).toFixed(1) : null })
  }
  const history = [...byDay.values()]
  const latRows = [['event_to_score', 'Event → new score'], ['trigger_to_action', 'Trigger → action taken']].filter(([k]) => lat[k])
  const feed = data.feed || []
  const sr = st?.score_refresh
  const ctl = last?.learned?.control || {}
  const own = (lm.own_effects || []).filter(e => Math.abs(e.points) >= 0.1 && !e.input.startsWith('away'))
  const imp = data.impact

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-white">Learning loop</h1>
          <p className="text-slate-400 text-sm mt-1 max-w-3xl">
            The CRM learns from what happens after its own actions, and is told what it did to each lead, so it never counts
            its own emails, coupons and calls as lead quality. A new model replaces the old one only if it predicts the
            untouched control group better: the {pct(data.settings.control_share)} of leads the CRM never contacts.
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => retrain(true)} disabled={busy} className="text-sm border border-white/15 text-slate-300 rounded-xl px-4 py-2.5 hover:border-white/40 disabled:opacity-50"
            title="Trains and compares the models but does not replace anything">Dry run</button>
          <button onClick={() => retrain(false)} disabled={busy} className="btn text-sm">{busy ? '⏳ Learning…' : '🔁 Retrain now'}</button>
        </div>
      </div>

      {result && (
        <div className={`card p-4 mb-6 text-sm ${result.ok ? 'text-slate-300' : 'text-red-400'}`}>
          {result.ok ? (
            <>
              <p className="font-semibold text-white">{result.status === 'dry_run' ? 'Dry run finished (nothing replaced).'
                : result.status === 'nothing_new' ? 'Nothing new to learn yet.' : result.status === 'busy' ? 'A learning run is already in progress.'
                : `Learning run ${result.run_id ?? ''} finished.`}</p>
              {result.status === 'nothing_new' ? <p className="mt-1 text-slate-400">{result.message}</p> : result.status !== 'busy' && (
              <p className="mt-1">{num(result.outcomes_known)} decision points with a known outcome · {result.control_people ?? 0} control-group people with a known outcome ·
                lead model: <Chip d={result.lead_decision} /> · next-best-action: <Chip d={result.nba?.decision} /></p>)}
              {result.note && <p className="text-slate-400 text-xs mt-1">{result.note}</p>}
              {result.nba?.note && <p className="text-slate-400 text-xs mt-1">Next-best-action: {result.nba.note}</p>}
            </>
          ) : <p>{result.note}</p>}
        </div>
      )}

      {/* The loop, live */}
      <div className="flex flex-wrap items-stretch gap-2 mb-2">
        <Step icon="👀" title="1 · Watch" value={num(c.events_today)} sub="website events today (video, pricing, cart …)" />
        <Step icon="🎯" title="2 · Score" value={num(c.scored_today)} sub={`re-scores today — every event updates the score${sr ? `; everyone re-scored ${String(sr.at || '').slice(11, 16)} (${sr.model_version})` : ''}`} />
        <Step icon="🧠" title="3 · Decide" value={num(c.decisions_total)} sub={`next-best-action decisions · ${pct(c.decisions_total ? c.decisions_random / c.decisions_total : null)} random (to learn) · ${num(c.decisions_today)} today`} />
        <Step icon="✉️" title="4 · Act & observe" value={num(c.purchases_total)} sub={`purchases · ${num(c.control_group)} people in the untouched control group (never contacted) · ${num(c.emails_today)} emails today`} />
        <Step icon="🔁" title="5 · Learn" highlight value={last ? day(last.as_of) : 'not yet'}
          sub={last ? `last run: lead model ${DECISION[last.lead_decision]?.text || last.lead_decision}${st ? ` · next run by itself after ${Math.max(0, st.min_new_outcomes - st.new_outcomes)} more outcomes (${st.new_outcomes}/${st.min_new_outcomes})` : ''}`
            : `runs by itself when ${data.settings.min_new_outcomes}+ outcomes are known`} />
      </div>
      <p className="text-slate-500 text-xs mb-2">↻ What step 5 learns goes straight back into step 2: after a model switch every lead is re-scored by itself. Outcome = bought within {data.settings.window_days} days.
        {' '}Exploration {pct(data.settings.exploration_rate)} · swap only when better in ≥ {pct(data.settings.swap_confidence)} of resamples.</p>
      <p className="text-slate-500 text-xs mb-8">One pool of learners: {num(c.simulated_people)} simulated (the 6-month starting history and the ones who keep using the website live) and {num(c.real_people)} who signed up themselves. The loop learns from all of them the same way. Runs made while the starting history was generated are marked “simulated history” below.</p>

      <div className="grid lg:grid-cols-2 gap-6 mb-6">
        {/* Is it fooling itself? */}
        <div className="card p-6">
          <h2 className="font-display text-lg font-bold text-white mb-1">Is the model fooling itself?</h2>
          <p className="text-slate-500 text-xs mb-4">Latest run, {day(last?.as_of)}. A normal CRM checks its model on all live outcomes — but those were shaped by its own follow-ups.
            Ours is checked on the untouched control group, whose outcomes nobody's follow-ups shaped.</p>
          {!last || last.challenger_true_auc == null ? (
            <p className="text-slate-400 text-sm">Not enough people of the untouched control group have a known outcome yet ({num(ctl.people || 0)} so far; the check needs 20).</p>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-3 mb-4">
                <div className="bg-white/5 rounded-xl p-3">
                  <p className="text-slate-500 text-[11px] uppercase tracking-wide">Naive retrain expects</p>
                  <p className="font-display text-3xl font-extrabold text-slate-300">{pct(ctl.predicted?.naive, 1)}</p>
                  <p className="text-slate-500 text-[11px]">of the untouched leads to buy</p>
                </div>
                <div className="bg-ember/10 border border-ember/30 rounded-xl p-3">
                  <p className="text-ember text-[11px] uppercase tracking-wide">Ours expects</p>
                  <p className="font-display text-3xl font-extrabold text-white">{pct(ctl.predicted?.challenger, 1)}</p>
                  <p className="text-slate-400 text-[11px]">of the same leads</p>
                </div>
                <div className="bg-white/5 rounded-xl p-3">
                  <p className="text-slate-500 text-[11px] uppercase tracking-wide">They actually bought</p>
                  <p className="font-display text-3xl font-extrabold text-green-400">{pct(ctl.actual, 1)}</p>
                  <p className="text-slate-500 text-[11px]">{num(ctl.people)} control people with a known outcome ({num(last.random_slice)} decision points)</p>
                </div>
              </div>
              {ctl.actual > 0 && ctl.predicted?.naive != null && <p className="text-slate-300 text-sm mb-2">A normal retrain overstates leads by{' '}
                <span className="text-white font-semibold">{((ctl.predicted.naive / ctl.actual - 1) * 100).toFixed(0)}%</span>, because it counts our own follow-ups as lead quality; ours is off by{' '}
                <span className="text-white font-semibold">{((ctl.predicted.challenger / ctl.actual - 1) * 100).toFixed(0)}%</span>.
                {' '}<span className="text-slate-500 text-xs">(Some gap is expected for both: the score is the chance to buy if we do nothing now, and these leads also get nothing later.)</span></p>}
              {last.own_effect_share != null && <p className="text-slate-300 text-sm mb-3">Own effect: <span className="text-white font-semibold">{pct(last.own_effect_share)}</span> of the buying chance of leads we acted on came from the e-mail, coupon or call the CRM sent at that moment — a naive retrain counts that as “lead quality”.</p>}
              <table className="w-full text-xs">
                <thead><tr className="text-slate-500 text-left"><th className="py-1">Model</th><th>Fit on live data<br/>(log-loss)</th><th>Control group<br/>(log-loss)</th><th>Control AUC</th><th>Control: predicted<br/>vs bought</th></tr></thead>
                <tbody>
                  <tr className="border-t border-white/5 text-slate-400"><td className="py-1.5">Current (champion)</td><td>—</td><td>{ll(last.champion_true_logloss)}</td><td>{auc(last.champion_true_auc)}</td><td>{pct(ctl.predicted?.champion, 1)} vs {pct(ctl.actual, 1)}</td></tr>
                  <tr className="border-t border-white/5 text-white"><td className="py-1.5">New — ours (told what the CRM did)</td><td>{ll(last.challenger_live_logloss)}</td><td>{ll(last.challenger_true_logloss)}</td><td>{auc(last.challenger_true_auc)}</td><td>{pct(ctl.predicted?.challenger, 1)} vs {pct(ctl.actual, 1)}</td></tr>
                  <tr className="border-t border-white/5 text-slate-400"><td className="py-1.5">New — naive (how CRMs retrain)</td><td>{ll(last.naive_live_logloss)}</td><td>{ll(last.naive_true_logloss)}</td><td>{auc(last.naive_true_auc)}</td><td>{pct(ctl.predicted?.naive, 1)} vs {pct(ctl.actual, 1)}</td></tr>
                </tbody>
              </table>
              <p className="text-slate-500 text-[11px] mt-2">Lower log-loss is better. “Predicted vs bought”: how often each model expected the control group to buy within {data.settings.window_days} days, against how often they did.</p>
              <p className="text-slate-400 text-xs mt-3">
                {last.naive_would_pick ? '⚠️ Picking the model that fits live data best would have chosen the naive one. ' : 'Fit on live data would not have picked the naive model this time. '}
                Our loop decided on the honest check: <Chip d={last.lead_decision} />{last.lead_prob_better != null ? ` (better in ${pct(last.lead_prob_better)} of resamples)` : ''}.
              </p>
            </>
          )}
        </div>

        {/* What it has learned */}
        <div className="card p-6">
          <h2 className="font-display text-lg font-bold text-white mb-1">What the loop has learned</h2>
          <p className="text-slate-500 text-xs mb-3">
            Base model: trained once on {num(lm.trained_on?.simulated_leads)} simulated leads with every website signal (AUC {auc(lm.metrics?.roc_auc)}).
            Learned on top from {num(lm.live?.outcomes_used || 0)} outcomes of this CRM's own history
            {lm.live ? ` · recalibration ×${Number(lm.live.slope ?? 1).toFixed(2)}, ${Number(lm.live.intercept ?? 0) >= 0 ? '+' : ''}${Number(lm.live.intercept ?? 0).toFixed(2)}` : ''}.
          </p>
          {learned.length === 0 ? <p className="text-slate-400 text-sm">Nothing learned yet — the corrections start at zero until outcomes are known.</p> : (
            <ResponsiveContainer width="100%" height={Math.max(180, learned.length * 24)}>
              <BarChart data={learned} layout="vertical" margin={{ top: 0, right: 20, left: 10, bottom: 0 }}>
                <XAxis type="number" tick={{ fill: '#94a3b8', fontSize: 11 }} unit=" pts" />
                <YAxis type="category" dataKey="label" width={160} tick={{ fill: '#cbd5e1', fontSize: 11 }} />
                <Tooltip contentStyle={TIP} formatter={v => [`${v} points for a typical lead`, 'Correction learned']} />
                <ReferenceLine x={0} stroke="#475569" />
                <Bar dataKey="points" radius={[0, 4, 4, 0]}>
                  {learned.map((e, i) => <Cell key={i} fill={e.points >= 0 ? '#22c55e' : '#ef4444'} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
          {learned.some(e => e.signal === 'EmailEngagement' && e.points < 0) && (
            <p className="text-slate-500 text-[11px] mt-2">“Clicked our emails” comes out negative: people who keep getting follow-ups without buying stay in the
              data longer and collect clicks, so clicks look worse than they are. The score therefore never lets a click lower someone's chance (a click
              counts at least zero).</p>
          )}
          <p className="text-slate-500 text-[11px] mt-2">These are corrections on top of the base model, learned from this CRM's own outcomes; the base model
            already counts every signal. Time since the last visit is learned the same way and lowers the score when someone goes quiet.</p>
        </div>
      </div>

      <div className="grid lg:grid-cols-2 gap-6 mb-6">
        {/* What our own actions add */}
        <div className="card p-6">
          <h2 className="font-display text-lg font-bold text-white mb-1">What our own actions add</h2>
          <p className="text-slate-500 text-xs mb-3">Learned by the loop and then switched off in the score, so they never count as lead quality
            (points of buying chance for a typical lead).</p>
          {own.length === 0 ? <p className="text-slate-400 text-sm">Not learned yet — the first model swap stores them.</p> : (
            <table className="w-full text-xs">
              <tbody>{own.map(e => (
                <tr key={e.input} className="border-t border-white/5 text-slate-300">
                  <td className="py-1.5">{e.label}</td>
                  <td className={`text-right font-mono ${e.points >= 0 ? 'text-green-400' : 'text-red-400'}`}>{e.points >= 0 ? '+' : ''}{e.points} pts</td>
                </tr>))}
              </tbody>
            </table>
          )}
        </div>
        {/* The CRM's total impact */}
        <div className="card p-6">
          <h2 className="font-display text-lg font-bold text-white mb-1">The CRM's total impact</h2>
          <p className="text-slate-500 text-xs mb-3">Leads the CRM worked on against the untouched control group: share who bought within {imp?.days ?? 30} days
            of signing up (people who signed up at least that long ago).</p>
          {!imp || !imp.control?.people ? <p className="text-slate-400 text-sm">No control-group people with a known outcome yet.</p> : (
            <>
              <div className="grid grid-cols-2 gap-3 mb-3">
                <div className="bg-white/5 rounded-xl p-3"><p className="text-slate-500 text-[11px] uppercase tracking-wide">Worked on</p>
                  <p className="font-display text-2xl font-extrabold text-white">{pct(imp.worked_on.rate, 1)}</p><p className="text-slate-500 text-[11px]">{num(imp.worked_on.people)} people</p></div>
                <div className="bg-white/5 rounded-xl p-3"><p className="text-slate-500 text-[11px] uppercase tracking-wide">Control group</p>
                  <p className="font-display text-2xl font-extrabold text-white">{pct(imp.control.rate, 1)}</p><p className="text-slate-500 text-[11px]">{num(imp.control.people)} people</p></div>
              </div>
              {imp.lift != null && <p className="text-slate-300 text-sm">The CRM adds <span className="text-white font-semibold">{imp.lift >= 0 ? '+' : ''}{(imp.lift * 100).toFixed(1)} pts</span>
                {' '}(95% interval {(imp.lift_ci[0] * 100).toFixed(1)} to {(imp.lift_ci[1] * 100).toFixed(1)} pts){imp.lift_ci[0] <= 0 && imp.lift_ci[1] >= 0 ? ' — not yet clear: the control group is still small.' : '.'}</p>}
            </>
          )}
        </div>
      </div>

      {/* Over time */}
      {history.length > 1 && (
        <div className="card p-6 mb-6">
          <h2 className="font-display text-lg font-bold text-white mb-1">The loop over time: who is fooled?</h2>
          <p className="text-slate-500 text-xs mb-3">Each point is a learning run: the share of the untouched control group each model expected to buy within
            {' '}{data.settings.window_days} days, and the share that did. Some gap is expected for both (the score means “if we do nothing now”, and these leads
            {' '}also get nothing later); the naive line's extra gap is self-deception.</p>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={history} margin={{ top: 5, right: 20, left: -10, bottom: 0 }}>
              <CartesianGrid stroke="rgba(255,255,255,0.05)" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} unit="%" />
              <Tooltip contentStyle={TIP} formatter={(v, n) => [v == null ? '—' : `${v}%`, n]} />
              <Legend wrapperStyle={{ color: '#94a3b8', fontSize: 11 }} />
              <Line type="monotone" dataKey="naive" name="Naive retrain expects" stroke="#64748b" strokeDasharray="5 4" dot />
              <Line type="monotone" dataKey="ours" name="Ours expects" stroke="#f97316" strokeWidth={2} dot />
              <Line type="monotone" dataKey="actual" name="Actually bought" stroke="#22c55e" strokeWidth={2} dot />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      <div className="grid lg:grid-cols-3 gap-6 mb-6">
        {/* Runs */}
        <div className="card p-6 lg:col-span-2">
          <h2 className="font-display text-lg font-bold text-white mb-3">Learning runs</h2>
          <p className="text-slate-500 text-xs mb-3">“Outcomes” = decision points whose 14-day result is known (next-best-action decisions plus campaign and A/B emails). “Control group” = decision points of people the CRM never contacts.</p>
          {runs.length === 0 ? <p className="text-slate-400 text-sm">No runs yet. The loop runs automatically when {data.settings.min_new_outcomes}+ new outcomes are known, or press “Retrain now”.</p> : (
            <div className="overflow-x-auto max-h-96 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-[#0B1426]"><tr className="text-slate-500 text-left">
                  <th className="py-1.5 pr-3">Date</th><th className="pr-3">Outcomes</th><th className="pr-3">Control group</th>
                  <th className="pr-3">Lead model</th><th className="pr-3">Next-best-action</th><th>Why</th></tr></thead>
                <tbody>{runs.map(r => (
                  <tr key={r.id} className="border-t border-white/5 text-slate-300 align-top">
                    <td className="py-1.5 pr-3 whitespace-nowrap">{day(r.as_of)}{r.simulated ? <span className="block text-[10px] text-slate-500" title="Run while the 6-month starting history was generated">simulated history</span> : null}</td>
                    <td className="pr-3">{num(r.outcomes_known)}<span className="block text-[10px] text-slate-500">+{num(r.new_outcomes)} new</span></td>
                    <td className="pr-3">{num(r.random_slice)}<span className="block text-[10px] text-slate-500">{num(r.random_slice_buyers)} bought</span></td>
                    <td className="pr-3"><Chip d={r.lead_decision} />{r.lead_prob_better != null && <span className="block text-[10px] text-slate-500 mt-0.5">better in {pct(r.lead_prob_better)}</span>}</td>
                    <td className="pr-3"><Chip d={r.nba_decision} /></td>
                    <td className="text-slate-400">{r.note}{r.nba?.note ? <span className="block text-slate-500 mt-0.5">NBA: {r.nba.note}</span> : null}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Speed + feed */}
        <div className="space-y-6">
          <div className="card p-6">
            <h2 className="font-display text-lg font-bold text-white mb-3">Real-time</h2>
            {latRows.length === 0 ? <p className="text-slate-400 text-sm">Response times appear after the first website events since the server started (open the website and click around).</p> : (
              <table className="w-full text-xs">
                <thead><tr className="text-slate-500 text-left"><th className="py-1">Step</th><th>Median</th><th>95%</th><th>n</th></tr></thead>
                <tbody>
                  {latRows.map(([k, label]) => (
                    <tr key={k} className="border-t border-white/5 text-slate-300"><td className="py-1.5">{label}</td><td>{lat[k].median_ms} ms</td><td>{lat[k].p95_ms} ms</td><td>{lat[k].count}</td></tr>
                  ))}
                </tbody>
              </table>
            )}
            {!st && <p className="text-slate-500 text-[11px] mt-2">User backend not reachable — live counts still work.</p>}
          </div>
          <div className="card p-6">
            <div className="flex items-center justify-between mb-3">
              <h2 className="font-display text-lg font-bold text-white">Live activity</h2>
              <span className="text-[11px] text-slate-500">everyone · simulated learners tagged</span>
            </div>
            <div className="space-y-1.5 max-h-72 overflow-y-auto">
              {feed.length === 0 && <p className="text-slate-500 text-xs">No activity yet. Open the website, sign up and click around: it appears here within seconds.</p>}
              {feed.map((f, i) => (
                <div key={i} className="text-xs text-slate-400 flex gap-2">
                  <span className="text-slate-600 w-28 flex-shrink-0">{String(f.at || '').slice(5, 16)}</span>
                  <span className="flex-shrink-0">{{ event: '👀', decision: '🧠', purchase: '💰', learning: '🔁' }[f.kind] || '•'}</span>
                  <span className="text-slate-300 truncate">{f.name ? `${f.name}: ` : ''}{String(f.what || '').replaceAll('_', ' ')}</span>
                  {f.simulated && <span className="text-[10px] px-1.5 rounded bg-white/10 text-slate-500 flex-shrink-0">simulated</span>}
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      <p className="text-slate-500 text-xs">
        Model health per tier and the next-best-action report are on the <Link to="/" className="text-sky-accent hover:underline">Dashboard</Link>;
        how leads moved through the stages is on <Link to="/journeys" className="text-sky-accent hover:underline">Journeys</Link>.
      </p>
    </div>
  )
}
