import { useEffect, useState } from 'react'
import { Link }                from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, ResponsiveContainer, Legend } from 'recharts'
import { getStats, exportCsv, getCampaignInfluence, getModelHealth, getNbaPerformance, runAutomations, getForecast } from '../utils/api'

const TIER_COLORS = {
  'Target Immediately':'#f97316',
  'Nurture via Email/WhatsApp':'#f59e0b',
  'Marketing Campaign':'#eab308',
  'Low Priority':'#64748b',
}
const SCORE_COLORS = ['#64748b','#3b82f6','#f59e0b','#f97316','#ef4444']

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

      {stats.demo_users > 0 && (
        <div className="card p-4 mb-6 text-xs text-slate-400 border-sky-accent/30">
          Includes the starting history: <span className="text-white font-semibold">{stats.demo_users} simulated learners</span> over
          six months (emails ending @demo.xeducation.test, marked “simulated” in Leads). Their behaviour and purchases come from
          the simulator, so these numbers show how the system works, not real customer results; real sign-ups are added on top.
          To delete it: <span className="font-mono">python ml/generate_history.py --remove</span>.
        </div>
      )}

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
                  <tr key={a} className="border-t border-white/5 text-slate-300"><td className="py-1.5">{a}</td><td>{v.decisions}</td><td>{v.explore}</td><td>{v.converted}/{v.known_outcome}</td></tr>
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
          { label:'People (leads)',  value: stats.total_leads,     icon:'👥', color:'text-white' },
          { label:'Avg Lead Score',  value: `${stats.avg_lead_score}/100`, icon:'⭐', color:'text-ember' },
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
