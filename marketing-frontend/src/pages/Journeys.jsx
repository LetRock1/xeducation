import { useEffect, useState } from 'react'
import { Sankey, Tooltip, ResponsiveContainer, Layer, Rectangle } from 'recharts'
import { getJourneys } from '../utils/api'
import { stageLabel } from '../utils/labels'

const TIP = { background:'#0B1426', border:'1px solid rgba(255,255,255,0.1)', borderRadius:12, color:'#e2e8f0' }
const TIERS = ['', 'Target Immediately', 'Nurture via Email/WhatsApp', 'Marketing Campaign', 'Low Priority']
const LAYER_COLOR = { stage: '#38BDF8', group: '#f97316', reaction: '#a78bfa', outcome: '#22c55e' }
const pct = x => (x == null ? '—' : `${(x * 100).toFixed(0)}%`)
const STAGE_TEXT = {
  Lead: 'signed up', Engaged: 'video, brochure, testimonials, webinar or 2nd visit', MQL: 'pricing, wishlist or chat',
  SQL: 'enquiry, callback, cart or checkout', Customer: 'bought',
}

function Node({ x, y, width, height, index, payload, containerWidth }) {
  const isOut = x + width + 6 > containerWidth - 140
  const color = LAYER_COLOR[payload.layer] || '#64748b'
  return (
    <Layer key={`n${index}`}>
      <Rectangle x={x} y={y} width={width} height={height} fill={color} fillOpacity={payload.name === 'Bought' ? 1 : 0.85} radius={2} />
      <text textAnchor={isOut ? 'end' : 'start'} x={isOut ? x - 6 : x + width + 6} y={y + height / 2} fontSize={12} fill="#e2e8f0" dominantBaseline="middle">
        {payload.layer === 'stage' ? stageLabel(payload.name) : payload.name} <tspan fill="#94a3b8">({payload.value})</tspan>
      </text>
    </Layer>
  )
}

function Link_({ sourceX, targetX, sourceY, targetY, sourceControlX, targetControlX, linkWidth, index, payload }) {
  const good = payload?.target?.name === 'Bought'
  return (
    <path key={`l${index}`} d={`M${sourceX},${sourceY} C${sourceControlX},${sourceY} ${targetControlX},${targetY} ${targetX},${targetY}`}
      fill="none" stroke={good ? '#22c55e' : '#64748b'} strokeOpacity={good ? 0.45 : 0.22} strokeWidth={Math.max(1, linkWidth)} />
  )
}

export default function Journeys() {
  const [days, setDays] = useState(180)
  const [tier, setTier] = useState('')
  const [data, setData] = useState(null)
  const [err, setErr] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    getJourneys(days, tier).then(r => { setData(r.data); setErr('') })
      .catch(e => setErr(e.response?.data?.detail || 'Could not load journeys.'))
      .finally(() => setLoading(false))
  }, [days, tier])

  const sankey = data?.sankey
  const funnel = data?.funnel?.stages || []
  const top = funnel[0]?.people || 0

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-4 mb-6">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-white">Journeys</h1>
          <p className="text-slate-400 text-sm mt-1 max-w-3xl">What happened to past leads: the stage they were in, what the team did, how they
            reacted in the next 3 days and whether they bought. This history is what the what-if paths on each lead learn from.
            It covers everyone, simulated learners included. Stages are the standard CRM ones: MQL = marketing-qualified (showed interest),
            SQL = sales-qualified (ready to buy).</p>
        </div>
        <div className="flex gap-2">
          <select value={days} onChange={e => setDays(Number(e.target.value))} className="inp !w-auto !py-2">
            {[30, 90, 180, 365].map(d => <option key={d} value={d}>Last {d} days</option>)}
          </select>
          <select value={tier} onChange={e => setTier(e.target.value)} className="inp !w-auto !py-2">
            {TIERS.map(t => <option key={t} value={t}>{t || 'All tiers'}</option>)}
          </select>
        </div>
      </div>
      {err && <p className="text-red-400 mb-4">{err}</p>}
      {loading && !data && <div className="flex items-center justify-center h-64"><div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin" /></div>}

      {data && (
        <>
          {/* Funnel */}
          <div className="card p-6 mb-6">
            <h2 className="font-display text-lg font-bold text-white mb-1">Lifecycle funnel</h2>
            <p className="text-slate-500 text-xs mb-4">People who signed up in the period and the furthest stage they reached (standard CRM lifecycle stages).</p>
            <div className="space-y-2">
              {funnel.map((s, i) => (
                <div key={s.stage} className="flex items-center gap-3">
                  <div className="w-32 text-sm text-white font-semibold">{stageLabel(s.stage)}</div>
                  <div className="flex-1 bg-white/5 rounded-lg h-8 overflow-hidden">
                    <div className="h-8 rounded-lg flex items-center px-3 text-xs text-navy font-bold"
                      style={{ width: `${top ? Math.max(4, (s.people / top) * 100) : 0}%`, background: i === funnel.length - 1 ? '#22c55e' : '#38BDF8' }}>
                      {s.people.toLocaleString()}
                    </div>
                  </div>
                  <div className="w-56 text-xs text-slate-400">
                    {s.from_previous != null ? `${pct(s.from_previous)} of the stage before` : 'everyone who signed up'}
                    <span className="block text-slate-600">{STAGE_TEXT[s.stage]}</span>
                  </div>
                </div>
              ))}
            </div>
            {data.dropoffs?.length > 0 && (
              <p className="text-slate-300 text-sm mt-4">Biggest drop-off: <span className="text-white font-semibold">{pct(data.dropoffs[0].lost_share)}</span> of
                {' '}{data.dropoffs[0].from} leads never reached {data.dropoffs[0].to} ({data.dropoffs[0].lost.toLocaleString()} people).</p>
            )}
          </div>

          {/* Sankey */}
          <div className="card p-6 mb-6">
            <div className="flex flex-wrap items-baseline justify-between gap-2 mb-2">
              <h2 className="font-display text-lg font-bold text-white">Journey map</h2>
              <p className="text-slate-500 text-xs">{(data.with_outcome || 0).toLocaleString()} team decisions with a known outcome</p>
            </div>
            <div className="flex flex-wrap gap-4 text-[11px] text-slate-400 mb-2">
              {[['stage', 'Stage when the team acted'], ['group', 'What the team did'], ['reaction', 'Reaction in 3 days'], ['outcome', 'Outcome (14 days)']].map(([k, l]) => (
                <span key={k} className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-sm" style={{ background: LAYER_COLOR[k] }} />{l}</span>
              ))}
              <span className="flex items-center gap-1.5"><span className="w-4 h-0.5 bg-green-500" />flows that ended in a purchase</span>
            </div>
            {!sankey?.links?.length ? <p className="text-slate-400 text-sm">No decisions with a known outcome in this period yet.</p> : (
              <ResponsiveContainer width="100%" height={460}>
                <Sankey data={sankey} nodePadding={18} nodeWidth={12} margin={{ top: 10, right: 150, bottom: 10, left: 10 }}
                  node={<Node containerWidth={1000} />} link={<Link_ />} iterations={64}>
                  <Tooltip contentStyle={TIP} formatter={(v, n, p) => {
                    const pl = p?.payload?.payload
                    return [pl?.conversion != null ? `${v} decisions · ${pct(pl.conversion)} bought` : `${v}`, '']
                  }} />
                </Sankey>
              </ResponsiveContainer>
            )}
          </div>

          <div className="grid lg:grid-cols-2 gap-6">
            {/* Top paths */}
            <div className="card p-6">
              <h2 className="font-display text-lg font-bold text-white mb-1">Top converting paths</h2>
              <p className="text-slate-500 text-xs mb-3">Stage → what the team did → how the learner reacted. “Fair” rate is re-weighted by how likely each decision was, so it is not skewed by who the model chose.</p>
              <table className="w-full text-xs">
                <thead><tr className="text-slate-500 text-left"><th className="py-1">Path</th><th>n</th><th>Bought</th><th>Fair rate</th></tr></thead>
                <tbody>{(data.top_paths || []).map((p, i) => (
                  <tr key={i} className="border-t border-white/5 text-slate-300">
                    <td className="py-1.5"><span className="text-sky-accent">{stageLabel(p.stage)}</span> → {p.action_label} → <span className="text-violet-300">{p.reaction_label}</span></td>
                    <td>{p.n}</td><td className="text-green-400">{pct(p.conversion)}</td><td>{pct(p.conversion_weighted)}</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
            {/* Action effects */}
            <div className="card p-6">
              <h2 className="font-display text-lg font-bold text-white mb-1">What each step adds, by stage</h2>
              <p className="text-slate-500 text-xs mb-3">Fair buying rate after each team step vs doing nothing at the same stage (inverse-propensity weighted; small groups hidden).</p>
              <table className="w-full text-xs">
                <thead><tr className="text-slate-500 text-left"><th className="py-1">Stage</th><th>Step</th><th>n</th><th>Bought</th><th>vs nothing</th></tr></thead>
                <tbody>{(data.action_effects || []).sort((a, b) => b.lift - a.lift).map((e, i) => (
                  <tr key={i} className="border-t border-white/5 text-slate-300">
                    <td className="py-1.5">{stageLabel(e.stage)}</td><td>{e.label}</td><td>{e.n}</td><td>{pct(e.rate)}</td>
                    <td className={e.lift >= 0 ? 'text-green-400' : 'text-red-400'}>{e.lift >= 0 ? '+' : ''}{(e.lift * 100).toFixed(1)} pts</td>
                  </tr>))}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
