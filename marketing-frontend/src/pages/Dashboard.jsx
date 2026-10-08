import { useEffect, useState } from 'react'
import { Link }                from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, ResponsiveContainer, Legend } from 'recharts'
import { getStats, exportCsv, getCampaignInfluence, getModelHealth, getNbaPerformance, runAutomations, getForecast,
         getSimulation, simulationVisit, setSimulation } from '../utils/api'
import { actionLabel, ago } from '../utils/labels'

const TIER_COLORS = {
  'Target Immediately':'#f97316',
  'Nurture via Email/WhatsApp':'#f59e0b',
  'Marketing Campaign':'#eab308',
  'Low Priority':'#64748b',
}
const SCORE_COLORS = ['#64748b','#3b82f6','#f59e0b','#f97316','#ef4444']

// One pool of learners. Simulated learners (…@demo.xeducation.test) keep using the website in real time
// (ml/live_simulation.py): this card shows what they did lately and can send one to the website now.
function LearnersCard({ stats, onChange }) {
  const [sim, setSim] = useState(null)
  const [simErr, setSimErr] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const load = () => getSimulation().then(r => { setSim(r.data); setSimErr('') })
    .catch(e => setSimErr(e.response?.data?.detail || 'The user backend did not answer.'))
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t) }, [])

  async function sendOne(kind) {
    setBusy(true); setResult(null)
    try { const r = await simulationVisit(kind); setResult({ ok: true, ...r.data }); load() }
    catch (e) { setResult({ ok: false, message: e.response?.data?.detail || 'Could not send a learner.' }) }
    finally { setBusy(false) }
  }
  async function toggle() {
    setBusy(true)
    try { const r = await setSimulation(!sim?.enabled); setSim(r.data) } catch { /* shown by the next load */ }
    finally { setBusy(false) }
  }

  const people = stats.total_users ?? 0
  const simPeople = stats.simulated_people ?? stats.demo_users ?? 0
  const day = sim?.last_24h || {}
  return (
    <div className="card p-5 mb-6 border-sky-accent/30">
      <div className="flex flex-wrap items-start gap-x-10 gap-y-3">
        <div>
          <p className="text-slate-500 text-[11px] uppercase tracking-wide">Learners</p>
          <p className="text-white font-display text-2xl font-bold">{people.toLocaleString()}
            <span className="text-slate-400 text-sm font-normal"> · {(stats.customers ?? 0).toLocaleString()} customers · ₹{Math.round(stats.revenue || 0).toLocaleString('en-IN')} paid</span></p>
          <p className="text-slate-500 text-xs mt-0.5">{(stats.real_people ?? 0).toLocaleString()} signed up themselves ({stats.real_customers ?? 0} bought) · {simPeople.toLocaleString()} simulated ({(stats.simulated_customers ?? 0).toLocaleString()} bought)</p>
        </div>
        <div className="flex-1 min-w-[300px]">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-slate-500 text-[11px] uppercase tracking-wide">Simulated learners, live</p>
            {sim && (sim.enabled
              ? <span className="text-[10px] px-2 py-0.5 rounded-full bg-green-500/15 text-green-300">● using the website now{sim.learners?.on_site_now ? ` · ${sim.learners.on_site_now} on the site` : ''}</span>
              : <span className="text-[10px] px-2 py-0.5 rounded-full bg-amber-500/15 text-amber-300">paused</span>)}
            {simErr && <span className="text-[10px] text-red-400">{simErr}</span>}
          </div>
          {sim && <>
            <p className="text-slate-300 text-sm mt-1">Last 24 h: {day.visits ?? 0} visits · {day.email_clicks ?? 0} e-mail clicks · {day.purchases ?? 0} purchases · {day.signups ?? 0} new sign-ups · {day.advisor_tasks ?? 0} calls/WhatsApps by the simulated advisor</p>
            <p className="text-slate-500 text-xs mt-0.5">At this moment {sim.learners?.still_deciding ?? 0} of them are still deciding; expected per day ≈ {Math.round(sim.expected_per_day?.visits || 0)} return visits, {Math.round(sim.expected_per_day?.purchases || 0)} purchases, {Math.round(sim.expected_per_day?.signups || 0)} sign-ups (plus visits after e-mail clicks and calls).
              {sim.last_error && <span className="text-amber-300"> {sim.last_error}</span>}</p>
          </>}
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => sendOne('returning')} disabled={busy || !sim?.enabled} className="btn text-xs py-2 px-3 disabled:opacity-50"
            title="One simulated learner who is still deciding comes back to the website now (picked with their own chance of coming back). What they do there is drawn as for any visit.">▶ Send a learner to the website now</button>
          <button onClick={() => sendOne('signup')} disabled={busy || !sim?.enabled} className="text-xs border border-white/15 text-slate-300 rounded-lg px-3 py-2 hover:border-white/40 disabled:opacity-50"
            title="A new simulated person signs up now: sign-up, e-mailed code, profile, first visit">+ New sign-up now</button>
          {sim && <button onClick={toggle} disabled={busy} className="text-xs border border-white/15 text-slate-400 rounded-lg px-3 py-2 hover:border-white/40">{sim.enabled ? 'Pause' : 'Resume'}</button>}
        </div>
      </div>
      {result && (
        <p className={`text-sm mt-3 ${result.ok ? 'text-sky-accent' : 'text-red-400'}`}>{result.message}
          {result.ok && result.lead_id && <> <Link to={`/leads/${result.lead_id}`} className="underline">Open their lead page →</Link></>}</p>
      )}
      {sim?.recent?.length > 0 && (
        <ul className="mt-3 grid md:grid-cols-2 gap-x-6 gap-y-1 text-xs text-slate-400">
          {sim.recent.slice(0, 8).map((r, i) => (
            <li key={i} className="truncate" title={r.text}><span className="text-slate-600">{ago(r.at)} · </span>{r.text}</li>
          ))}
        </ul>
      )}
      <p className="text-[11px] text-slate-500 mt-3">One pool: the CRM scores, decides and learns for everyone the same way. Simulated learners use the website through
        the same API as a browser and follow a documented simulator (behaviour, reactions to e-mails, coupons and calls, buying); their
        e-mails are recorded but never delivered and their phone numbers are not real, so a simulated advisor handles their calls. They carry a
        small “simulated” tag everywhere.</p>
    </div>
  )
}

export default function Dashboard() {
  const [stats,   setStats]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [exporting, setExp]   = useState(false)
  const [influence, setInfluence] = useState(null)
  const [health,    setHealth]    = useState(null)
  const [nbaPerf,   setNbaPerf]   = useState(null)
  const [forecast,  setForecast]  = useState(null)
  const [running,   setRunning]   = useState(false)
  const [runResult, setRunResult] = useState(null)

  function loadAll() {
    getStats().then(r => setStats(r.data)).catch(() => {}).finally(() => setLoading(false))
    getCampaignInfluence().then(r => setInfluence(r.data.campaign_influence)).catch(() => {})
    getModelHealth().then(r => setHealth(r.data)).catch(() => {})
    getNbaPerformance().then(r => setNbaPerf(r.data)).catch(() => {})
    getForecast().then(r => setForecast(r.data)).catch(() => {})
  }
  useEffect(loadAll, [])

  async function handleRunAutomations() {
    setRunning(true); setRunResult(null)
    try {
      const r = await runAutomations()
      setRunResult({ ok: true, ...r.data })
      loadAll()
    } catch (e) {
      setRunResult({ ok: false, message: e.response?.data?.detail || 'Could not run the automations.' })
    } finally { setRunning(false) }
  }

  async function handleExport() {
    setExp(true)
    try {
      const r = await exportCsv()
      const url = URL.createObjectURL(new Blob([r.data]))
      const a   = document.createElement('a'); a.href = url
      a.download = `leads_${new Date().toISOString().slice(0,10)}.csv`
      a.click(); URL.revokeObjectURL(url)
    } catch {}
    finally { setExp(false) }
  }

  if (loading) return <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin"/></div>
  if (!stats)  return <p className="text-slate-500 text-center mt-20">Could not load stats. Make sure the marketing backend is running on port 8001.</p>

  const tierData  = Object.entries(stats.by_tier || {}).map(([name,value]) => ({ name: name==='Nurture via Email/WhatsApp'?'Nurture':name==='Marketing Campaign'?'Campaign':name==='Target Immediately'?'Target Now':name, value }))
  const scoreData = Object.entries(stats.score_distribution || {}).map(([range, count], i) => ({ range, count, fill: SCORE_COLORS[i] }))
  const tierPie   = Object.entries(stats.by_tier || {}).map(([name, value]) => ({ name, value }))

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-white">Marketing Intelligence</h1>
          <p className="text-slate-500 text-sm mt-1">X Education — Live Dashboard</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={handleRunAutomations} disabled={running}
            title="Runs the cart, checkout, wishlist and inactivity follow-ups now instead of waiting for the 5-minute timer"
            className="btn text-sm flex items-center gap-2 disabled:opacity-60">
            {running ? '⏳ Running…' : '⚡ Run automations now'}
          </button>
          <button onClick={handleExport} disabled={exporting}
            className="btn text-sm flex items-center gap-2">
            {exporting ? '⏳ Exporting…' : '⬇️ Export CSV'}
          </button>
        </div>
      </div>

      <LearnersCard stats={stats} onChange={loadAll} />

      {runResult && (
        <div className={`card p-4 mb-6 text-sm ${runResult.ok ? 'text-slate-300' : 'text-red-400'}`}>
          <p className="font-semibold">{runResult.message}</p>
          {runResult.decisions?.length > 0 && (
            <ul className="mt-2 space-y-1 text-xs text-slate-400">
              {runResult.decisions.map((d, i) => (
                <li key={i}>{d.name} · {d.trigger_reason.replace('_', ' ')} → <span className="text-white">{d.action.replaceAll('_', ' ')}</span>{d.policy === 'explore' ? ' (random — learning sample)' : ''}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Pipeline forecast — calibrated probabilities x course price */}
      {forecast && forecast.open_leads > 0 && (
        <div className="card p-5 mb-8">
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
            <h2 className="font-display text-lg font-bold text-white">Pipeline forecast</h2>
            <p className="text-slate-500 text-xs">{forecast.open_leads} people who have not bought yet</p>
          </div>
          <div className="grid md:grid-cols-3 gap-4 text-sm">
            <div>
              <p className="text-slate-500 text-xs">Expected revenue</p>
              <p className="font-display text-2xl font-extrabold text-green-400">₹{Math.round(forecast.expected_revenue).toLocaleString()}</p>
              <p className="text-slate-500 text-xs">90% range ₹{Math.round(forecast.range_90[0]).toLocaleString()} – ₹{Math.round(forecast.range_90[1]).toLocaleString()}</p>
            </div>
            <div>
              <p className="text-slate-500 text-xs">Expected new customers</p>
              <p className="font-display text-2xl font-extrabold text-white">{forecast.expected_customers}</p>
              <p className="text-slate-500 text-xs">90% range {forecast.customers_range_90[0]} – {forecast.customers_range_90[1]}</p>
            </div>
            <div className="space-y-1">
              {forecast.by_tier.map(t => (
                <div key={t.tier} className="flex justify-between text-xs text-slate-300 border-b border-white/5 py-0.5">
                  <span>{t.tier}</span><span>{t.leads} · ₹{t.expected_revenue.toLocaleString()}</span>
                </div>
              ))}
            </div>
          </div>
          <p className="text-slate-500 text-[11px] mt-3">{forecast.note}</p>
        </div>
      )}

      {/* Model health — closed-loop check of the ML model on real users */}
      {health && (
        <div className="card p-5 mb-8">
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
            <h2 className="font-display text-lg font-bold text-white">Model health</h2>
            <p className="text-slate-500 text-xs">
              {health.model
                ? `${health.model.version} · base model: ${health.model.model_type?.replace('_',' ')} (AUC ${health.model.metrics?.roc_auc} on held-out simulated leads) · live layer learned from ${(health.model.trained_on?.history_outcomes || 0).toLocaleString()} outcomes of this CRM`
                : 'No trained model yet — start-all.bat trains it on first start'}
            </p>
          </div>
          {health.by_tier.length === 0 ? (
            <p className="text-slate-400 text-sm">
              {health.snapshots_total} score snapshots recorded, none with a known outcome yet.
              Each purchase labels the earlier snapshots of that user as converted; after {health.window_days} days
              snapshots without a purchase count as not converted.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead><tr className="text-slate-500 text-left">
                  <th className="py-1 pr-4 font-medium">Tier</th><th className="py-1 pr-4 font-medium">Snapshots</th>
                  <th className="py-1 pr-4 font-medium">Predicted conversion</th><th className="py-1 font-medium">Actual conversion</th>
                </tr></thead>
                <tbody>
                  {health.by_tier.map(t => (
                    <tr key={t.tier} className="border-t border-white/5 text-slate-300">
                      <td className="py-1.5 pr-4">{t.tier}</td><td className="py-1.5 pr-4">{t.snapshots}</td>
                      <td className="py-1.5 pr-4">{(t.predicted_rate*100).toFixed(0)}%</td>
                      <td className="py-1.5">{(t.actual_rate*100).toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Next-best-action — what the uplift engine decided, and how it is doing */}
      {nbaPerf && (
        <div className="card p-5 mb-8">
          <div className="flex flex-wrap items-baseline justify-between gap-2 mb-3">
            <h2 className="font-display text-lg font-bold text-white">Next-best-action</h2>
            <p className="text-slate-500 text-xs">{nbaPerf.decisions_total} decisions · {nbaPerf.decisions_with_outcome} with known outcome</p>
          </div>
          {nbaPerf.decisions_total === 0 ? (
            <p className="text-slate-400 text-sm">No decisions yet. They are made when a cart or checkout is left, a wishlist goes cold, someone goes inactive, or an enquiry arrives.</p>
          ) : (
            <div className="grid md:grid-cols-2 gap-6 text-sm">
              <table className="w-full">
                <thead><tr className="text-slate-500 text-left"><th className="py-1 font-medium">Action</th><th className="font-medium">Decisions</th><th className="font-medium">Random (learning)</th><th className="font-medium">Bought</th></tr></thead>
                <tbody>{Object.entries(nbaPerf.by_action).map(([a, v]) => (
                  <tr key={a} className="border-t border-white/5 text-slate-300"><td className="py-1.5">{actionLabel(a)}</td><td>{v.decisions}</td><td>{v.explore}</td><td>{v.converted}/{v.known_outcome}</td></tr>
                ))}</tbody>
              </table>
              <div>
                <p className="text-slate-400 text-xs mb-2">Estimated profit per lead if every lead got this policy (inverse-propensity, logged outcomes)</p>
                {Object.entries(nbaPerf.policy_estimates).map(([k, v]) => (
                  <div key={k} className="flex justify-between gap-3 text-slate-300 py-1 border-b border-white/5">
                    <span>{k}</span>
                    <span className="text-right">
                      {v.snips_profit_per_lead == null ? '—' : `₹${Math.round(v.snips_profit_per_lead).toLocaleString()}`}
                      <span className="block text-[11px] text-slate-500">
                        {v.ci95 ? `95% CI ₹${Math.round(v.ci95[0]).toLocaleString()} – ₹${Math.round(v.ci95[1]).toLocaleString()} · ` : ''}{v.matched_decisions} matching decisions
                      </span>
                    </span>
                  </div>
                ))}
                <p className="text-slate-500 text-[11px] mt-2">{nbaPerf.note}</p>
              </div>
            </div>
          )}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { label:'People · customers', value: `${stats.total_leads} · ${stats.customers ?? 0}`, icon:'👥', color:'text-white' },
          { label:'Avg score (not bought yet)', value: `${stats.avg_lead_score}/100`, icon:'⭐', color:'text-ember' },
          { label:'Emails sent · clicked', value: `${stats.emails_sent} · ${stats.email_clicks ?? 0}`, icon:'✉️', color:'text-sky-accent' },
          { label:'Active Carts',    value: stats.active_carts,    icon:'🛒', color:'text-gold' },
          { label:'Open callbacks',  value: stats.open_callbacks ?? 0, icon:'📞', color:'text-sky-accent' },
          { label:'Purchases · revenue', value: `${stats.total_purchases} · ₹${Math.round(stats.revenue || 0).toLocaleString()}`, icon:'💰', color:'text-green-400' },
          { label:'Target Now',      value: stats.by_tier?.['Target Immediately'] || 0,         icon:'🔴', color:'text-red-400' },
          { label:'Nurture Queue',   value: stats.by_tier?.['Nurture via Email/WhatsApp'] || 0, icon:'🟠', color:'text-orange-400' },
        ].map(s => (
          <div key={s.label} className="card card-interactive p-5">
            <p className="text-xl mb-1">{s.icon}</p>
            <p className={`font-display text-3xl font-extrabold ${s.color}`}>{s.value}</p>
            <p className="text-slate-500 text-xs mt-1">{s.label}</p>
          </div>
        ))}
      </div>

      {/* Charts */}
      <div className="grid md:grid-cols-2 gap-6 mb-6">
        {/* Score Distribution Bar */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-white mb-4">Lead Score Distribution</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={scoreData} margin={{ top:0, right:0, left:-20, bottom:0 }}>
              <XAxis dataKey="range" tick={{ fill:'#94a3b8', fontSize:11 }}/>
              <YAxis tick={{ fill:'#94a3b8', fontSize:11 }}/>
              <Tooltip contentStyle={{ background:'#0B1426', border:'1px solid rgba(255,255,255,0.1)', borderRadius:12, color:'#e2e8f0' }}/>
              <Bar dataKey="count" radius={[4,4,0,0]}>
                {scoreData.map((e,i) => <Cell key={i} fill={e.fill}/>)}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>

        {/* Tier Pie */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-white mb-4">Leads by Tier</h3>
          <ResponsiveContainer width="100%" height={220}>
            <PieChart>
              <Pie data={tierPie} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, percent }) => `${(percent*100).toFixed(0)}%`} labelLine={false}>
                {tierPie.map((e,i) => <Cell key={i} fill={TIER_COLORS[e.name] || '#64748b'}/>)}
              </Pie>
              <Tooltip contentStyle={{ background:'#0B1426', border:'1px solid rgba(255,255,255,0.1)', borderRadius:12, color:'#e2e8f0' }} formatter={(v,n) => [v, n==='Nurture via Email/WhatsApp'?'Nurture':n]}/>
              <Legend wrapperStyle={{ color:'#94a3b8', fontSize:11 }} formatter={n => n==='Nurture via Email/WhatsApp'?'Nurture':n==='Marketing Campaign'?'Campaign':n}/>
            </PieChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Campaign Influence */}
      {influence && Object.keys(influence).length > 0 && (
        <div className="card p-6 mb-6">
          <h3 className="font-display font-semibold text-white mb-4">Campaign Influence</h3>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={Object.entries(influence).map(([trigger, v]) => ({ trigger, ...v }))} margin={{ top:0, right:0, left:-20, bottom:0 }}>
              <XAxis dataKey="trigger" tick={{ fill:'#94a3b8', fontSize:11 }}/>
              <YAxis tick={{ fill:'#94a3b8', fontSize:11 }}/>
              <Tooltip contentStyle={{ background:'#0B1426', border:'1px solid rgba(255,255,255,0.1)', borderRadius:12, color:'#e2e8f0' }}/>
              <Legend wrapperStyle={{ color:'#94a3b8', fontSize:11 }}/>
              <Bar dataKey="opens" fill="#38BDF8" radius={[4,4,0,0]}/>
              <Bar dataKey="clicks" fill="#f59e0b" radius={[4,4,0,0]}/>
              <Bar dataKey="influenced_conversions" fill="#22c55e" radius={[4,4,0,0]}/>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Quick links */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { to:'/leads?tier=Target Immediately',        label:'View Target Now Leads',  icon:'🔴', count: stats.by_tier?.['Target Immediately'] || 0 },
          { to:'/leads?tier=Nurture via Email/WhatsApp',label:'View Nurture Queue',     icon:'🟠', count: stats.by_tier?.['Nurture via Email/WhatsApp'] || 0 },
          { to:'/leads?sort=plv',                        label:'Priority Queue (High PLV)', icon:'💎', count: null },
          { to:'/campaigns',                             label:'Schedule Campaign',      icon:'📅', count: null },
          { to:'/ab-tests',                              label:'A/B Tests',              icon:'🧪', count: null },
          { to:'/qna',                                   label:'Answer Questions',       icon:'❓', count: null },
        ].map(q => (
          <Link key={q.to} to={q.to}
            className="card card-interactive p-5 hover:border-ember/50 group">
            <p className="text-2xl mb-2">{q.icon}</p>
            <p className="font-display text-sm font-semibold text-white group-hover:text-ember transition-colors">{q.label}</p>
            {q.count !== null && <p className="text-slate-400 text-xs mt-1">{q.count} leads</p>}
          </Link>
        ))}
      </div>
    </div>
  )
}
