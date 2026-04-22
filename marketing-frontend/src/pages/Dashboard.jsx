import { useEffect, useState } from 'react'
import { Link }                from 'react-router-dom'
import { BarChart, Bar, XAxis, YAxis, Tooltip, PieChart, Pie, Cell, ResponsiveContainer, Legend } from 'recharts'
import { getStats, exportCsv } from '../utils/api'

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

  useEffect(() => {
    getStats().then(r => setStats(r.data)).catch(() => {}).finally(() => setLoading(false))
  }, [])

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
        <button onClick={handleExport} disabled={exporting}
          className="btn text-sm flex items-center gap-2">
          {exporting ? '⏳ Exporting…' : '⬇️ Export CSV'}
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {[
          { label:'Total Leads',     value: stats.total_leads,     icon:'👥', color:'text-white' },
          { label:'Avg Lead Score',  value: `${stats.avg_lead_score}/100`, icon:'⭐', color:'text-ember' },
          { label:'Emails Sent',     value: stats.emails_sent,     icon:'✉️', color:'text-sky-accent' },
          { label:'Active Carts',    value: stats.active_carts,    icon:'🛒', color:'text-gold' },
          { label:'Total Users',     value: stats.total_users,     icon:'🔐', color:'text-green-400' },
          { label:'Purchases',       value: stats.total_purchases, icon:'💰', color:'text-green-400' },
          { label:'Target Now',      value: stats.by_tier?.['Target Immediately'] || 0,         icon:'🔴', color:'text-red-400' },
          { label:'Nurture Queue',   value: stats.by_tier?.['Nurture via Email/WhatsApp'] || 0, icon:'🟠', color:'text-orange-400' },
        ].map(s => (
          <div key={s.label} className="card p-5">
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

      {/* Quick links */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { to:'/leads?tier=Target Immediately',        label:'View Target Now Leads',  icon:'🔴', count: stats.by_tier?.['Target Immediately'] || 0 },
          { to:'/leads?tier=Nurture via Email/WhatsApp',label:'View Nurture Queue',     icon:'🟠', count: stats.by_tier?.['Nurture via Email/WhatsApp'] || 0 },
          { to:'/campaigns',                             label:'Schedule Campaign',      icon:'📅', count: null },
          { to:'/qna',                                   label:'Answer Questions',       icon:'❓', count: null },
        ].map(q => (
          <Link key={q.to} to={q.to}
            className="card p-5 hover:border-ember/50 transition-colors group">
            <p className="text-2xl mb-2">{q.icon}</p>
            <p className="font-display text-sm font-semibold text-white group-hover:text-ember transition-colors">{q.label}</p>
            {q.count !== null && <p className="text-slate-400 text-xs mt-1">{q.count} leads</p>}
          </Link>
        ))}
      </div>
    </div>
  )
}
