import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getLeads } from '../utils/api'

const TIERS = [
  { key:null,                         label:'All',       icon:'📋' },
  { key:'Target Immediately',         label:'Target Now',icon:'🔴' },
  { key:'Nurture via Email/WhatsApp', label:'Nurture',   icon:'🟠' },
  { key:'Marketing Campaign',         label:'Campaign',  icon:'🟡' },
  { key:'Low Priority',               label:'Low Prio',  icon:'⚪' },
]
const SC = s => s>=80?'text-red-400 bg-red-900/20':s>=60?'text-orange-400 bg-orange-900/20':s>=40?'text-yellow-400 bg-yellow-900/20':'text-slate-400 bg-slate-800'
const TC = a => a==='Target Immediately'?'bg-red-900/30 text-red-400':a==='Nurture via Email/WhatsApp'?'bg-orange-900/30 text-orange-400':a==='Marketing Campaign'?'bg-yellow-900/30 text-yellow-400':'bg-slate-800 text-slate-400'

export default function Leads() {
  const [params, setParams] = useSearchParams()
  const [leads,  setLeads]  = useState([])
  const [loading,setLoading]= useState(true)
  const [search, setSearch] = useState('')
  const tier = params.get('tier')

  useEffect(() => {
    setLoading(true)
    getLeads(tier, search).then(r => setLeads(r.data.leads)).catch(() => []).finally(() => setLoading(false))
  }, [tier, search])

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-2xl font-bold text-white">Leads</h1>
        <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search name, email, course…"
          className="inp w-64 text-sm"/>
      </div>

      {/* Tier tabs */}
      <div className="flex gap-2 flex-wrap mb-6">
        {TIERS.map(t => (
          <button key={String(t.key)} onClick={() => setParams(t.key?{tier:t.key}:{})}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-sm font-medium transition-all
              ${tier===t.key?'bg-ember text-white':'bg-white/5 border border-white/10 text-slate-400 hover:border-white/30'}`}>
            {t.icon} {t.label}
          </button>
        ))}
      </div>

      {/* Table */}
      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs text-slate-500 uppercase tracking-wide">
                {['Lead','Course','Occupation','Score','Tier','Trigger','Email','Detail'].map(h => (
                  <th key={h} className={`px-4 py-3 font-semibold ${h==='Detail'||h==='Score'?'text-center':'text-left'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading
                ? <tr><td colSpan={8} className="text-center py-12 text-slate-500">⏳ Loading leads…</td></tr>
                : !leads.length
                ? <tr><td colSpan={8} className="text-center py-12 text-slate-500">No leads found.</td></tr>
                : leads.map(l => (
                  <tr key={l.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-3.5">
                      <p className="font-semibold text-white">{l.name}</p>
                      <p className="text-slate-500 text-xs">{l.email}</p>
                    </td>
                    <td className="px-4 py-3.5 text-slate-400 text-xs max-w-[130px] truncate">{l.course_type}</td>
                    <td className="px-4 py-3.5 text-slate-400 text-xs">{l.current_occupation}</td>
                    <td className="px-4 py-3.5 text-center">
                      <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-bold ${SC(l.lead_score)}`}>{l.lead_score}</span>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`inline-block text-xs px-2.5 py-1 rounded-full font-medium ${TC(l.recommended_action)}`}>
                        {l.recommended_action==='Nurture via Email/WhatsApp'?'Nurture':l.recommended_action==='Marketing Campaign'?'Campaign':l.recommended_action==='Target Immediately'?'Target Now':l.recommended_action}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-500 text-xs">{l.trigger_reason}</td>
                    <td className="px-4 py-3.5 text-center text-xs">
                      {l.email_sent?<span className="text-green-400">✓ Sent</span>:<span className="text-slate-600">Pending</span>}
                    </td>
                    <td className="px-4 py-3.5 text-center">
                      <Link to={`/leads/${l.id}`} className="text-sky-accent text-xs hover:underline">View →</Link>
                    </td>
                  </tr>
                ))
              }
            </tbody>
          </table>
        </div>
        {leads.length > 0 && <div className="px-4 py-3 border-t border-white/10 text-slate-500 text-xs">{leads.length} leads shown</div>}
      </div>
    </div>
  )
}
