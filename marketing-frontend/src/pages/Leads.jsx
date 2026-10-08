import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { getLeads } from '../utils/api'
import { TIER_SHORT, triggerLabel } from '../utils/labels'

const TIERS = [
  { key:null,                         label:'All',       icon:'🔵' },
  { key:'Target Immediately',         label:'Target Now',icon:'🔴' },
  { key:'Nurture via Email/WhatsApp', label:'Nurture',   icon:'🟠' },
  { key:'Marketing Campaign',         label:'Campaign',  icon:'🟡' },
  { key:'Low Priority',               label:'Low Prio',  icon:'⚪' },
  { key:'Customers',                  label:'Customers', icon:'✅' },
]
const SEGMENTS = [
  { key: 'all', label: 'Everyone', help: 'Every learner: people who signed up themselves and simulated learners' },
  { key: 'real', label: 'Signed up themselves', help: 'People who signed up on the website themselves' },
  { key: 'simulated', label: 'Simulated', help: 'Simulated learners (…@demo.xeducation.test): the starting history and the ones who keep using the website live' },
]
const SC = s => s>=80?'text-red-400 bg-red-900/20':s>=60?'text-orange-400 bg-orange-900/20':s>=40?'text-yellow-400 bg-yellow-900/20':'text-slate-400 bg-slate-800'
const TC = a => a==='Target Immediately'?'bg-red-900/30 text-red-400':a==='Nurture via Email/WhatsApp'?'bg-orange-900/30 text-orange-400':a==='Marketing Campaign'?'bg-yellow-900/30 text-yellow-400':'bg-slate-800 text-slate-400'
const inr = v => `₹${Math.round(v || 0).toLocaleString('en-IN')}`

export default function Leads() {
  const [params, setParams] = useSearchParams()
  const [leads,  setLeads]  = useState([])
  const [counts, setCounts] = useState(null)
  const [matching, setMatching] = useState(0)
  const [loading,setLoading]= useState(true)
  const [search, setSearch] = useState('')
  const tier = params.get('tier')
  const sort = params.get('sort')
  const segment = params.get('segment') || 'all'

  const setParam = (k, v) => setParams(p => { const n = new URLSearchParams(p); v ? n.set(k, v) : n.delete(k); return n })

  useEffect(() => {
    let live = true
    const fetchIt = (spinner) => {
      if (spinner) setLoading(true)
      getLeads(tier, search, sort, segment).then(r => { if (live) { setLeads(r.data.leads); setCounts(r.data.counts); setMatching(r.data.matching ?? r.data.leads.length) } }).catch(() => {})
        .finally(() => { if (live) setLoading(false) })
    }
    const t = setTimeout(() => fetchIt(true), search ? 300 : 0)  // wait until typing pauses
    const poll = setInterval(() => fetchIt(false), 10000)          // live: new sign-ups and new scores appear by themselves
    return () => { live = false; clearTimeout(t); clearInterval(poll) }
  }, [tier, search, sort, segment])

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
        <h1 className="font-display text-2xl font-bold text-white">Leads</h1>
        <div className="flex flex-wrap gap-2">
          <input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Search name, email, course…"
            className="inp w-64 text-sm"/>
          {[[null, 'Newest'], ['score', 'Score'], ['plv', 'Value']].map(([key, label]) => (
            <button key={label} onClick={() => setParam('sort', key)}
              className={`px-3 py-2 rounded-xl text-sm font-medium transition-all
                ${(sort || null) === key ? 'bg-ember text-white' : 'bg-white/5 border border-white/10 text-slate-400 hover:border-white/30'}`}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* Who: everyone (default), or only one kind of learner */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {SEGMENTS.map(s => (
          <button key={s.key} onClick={() => setParam('segment', s.key === 'all' ? null : s.key)} title={s.help}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all ${segment === s.key ? 'bg-sky-500/20 border border-sky-500/50 text-sky-200' : 'bg-white/5 border border-white/10 text-slate-400 hover:border-white/30'}`}>
            {s.label}{counts && counts[s.key] != null ? ` (${counts[s.key].toLocaleString()})` : ''}
          </button>
        ))}
        <span className="text-[11px] text-slate-500">One pool: the CRM scores and decides for everyone the same way. Simulated learners keep using the website by themselves (Dashboard → Simulated learners); their e-mails are recorded, never delivered.</span>
      </div>

      {/* Tier tabs */}
      <div className="flex gap-2 flex-wrap mb-6">
        {TIERS.map(t => (
          <button key={String(t.key)} onClick={() => setParam('tier', t.key)}
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
                {['Person','Course','Occupation','Score','Value','Tier','Latest touch','Status','Detail'].map(h => (
                  <th key={h} className={`px-4 py-3 font-semibold ${h==='Detail'||h==='Score'?'text-center':'text-left'}`}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading
                ? <tr><td colSpan={9} className="text-center py-12 text-slate-500">
                    <span className="inline-block w-4 h-4 border-2 border-ember border-t-transparent rounded-full animate-spin align-middle mr-2"/>
                    Loading leads…
                  </td></tr>
                : !leads.length
                ? <tr><td colSpan={9} className="text-center py-12 text-slate-500">
                    {segment === 'real' && !search && !tier
                      ? <>No real learners yet. Sign up on the website (http://localhost:5173) and you will appear here within seconds.</>
                      : '🔍 No leads found.'}
                  </td></tr>
                : leads.map(l => (
                  <tr key={l.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-3.5">
                      <p className="font-semibold text-white">{l.name}
                        {l.simulated && <span className="ml-2 text-[10px] font-medium px-1.5 py-0.5 rounded bg-white/10 text-slate-400 align-middle" title="Simulated learner: uses the website by itself (documented simulator); e-mails to them are recorded, never delivered">simulated</span>}
                      </p>
                      <p className="text-slate-500 text-xs">{l.email}</p>
                    </td>
                    <td className="px-4 py-3.5 text-slate-400 text-xs max-w-[130px] truncate">{l.customer ? l.first_course : l.course_type}</td>
                    <td className="px-4 py-3.5 text-slate-400 text-xs">{l.current_occupation}</td>
                    <td className="px-4 py-3.5 text-center">
                      {l.customer
                        ? <span className="inline-block px-2.5 py-1 rounded-full text-xs font-bold text-green-400 bg-green-900/20" title="Bought: customers are not scored">✓</span>
                        : <span className={`inline-block px-2.5 py-1 rounded-full text-xs font-bold ${SC(l.lead_score)}`} title="Chance (%) to buy within 14 days if we do nothing">{Math.round(l.lead_score)}</span>}
                    </td>
                    <td className="px-4 py-3.5 text-slate-400 text-xs">{l.customer ? <span title="Money already paid">{inr(l.spent)} paid</span> : <span title="Chance × course price">{inr(l.plv)}</span>}</td>
                    <td className="px-4 py-3.5">
                      {l.customer
                        ? <span className="inline-block text-xs px-2.5 py-1 rounded-full font-medium bg-green-900/30 text-green-400">Customer</span>
                        : <span className={`inline-block text-xs px-2.5 py-1 rounded-full font-medium ${TC(l.recommended_action)}`}>{TIER_SHORT[l.recommended_action] || l.recommended_action}</span>}
                    </td>
                    <td className="px-4 py-3.5 text-slate-500 text-xs">{triggerLabel(l.trigger_reason)}{l.touches > 1 && <span className="text-slate-600"> · {l.touches} touches</span>}</td>
                    <td className="px-4 py-3.5 text-center text-xs space-y-1">
                      {l.customer && <span className="block text-green-400">Bought</span>}
                      {l.open_callbacks > 0 && <span className="block text-sky-accent">📞 Callback</span>}
                      {l.do_not_email === 'Yes' && <span className="block text-slate-500">Unsubscribed</span>}
                      {!l.customer && !l.open_callbacks && l.do_not_email !== 'Yes' && (l.email_sent ? <span className="text-green-400">Emailed</span> : <span className="text-slate-600">—</span>)}
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
        {leads.length > 0 && <div className="px-4 py-3 border-t border-white/10 text-slate-500 text-xs">
          {matching > leads.length ? `${leads.length.toLocaleString()} of ${matching.toLocaleString()} people shown (search, a tier or a sort finds the others)` : `${leads.length.toLocaleString()} people shown`} (one row per person). Score = chance to buy within 14 days if we do nothing, kept current automatically; customers show what they paid.</div>}
      </div>
    </div>
  )
}
