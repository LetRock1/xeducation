import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { getPipeline, moveCard, resetCard } from '../utils/api'

const STAGE_COLOR = {
  Lead: 'border-slate-500/40', Engaged: 'border-sky-500/40', MQL: 'border-violet-500/40',
  SQL: 'border-amber-500/40', Customer: 'border-green-500/40',
}
const STAGE_DOT = { Lead: 'bg-slate-400', Engaged: 'bg-sky-400', MQL: 'bg-violet-400', SQL: 'bg-amber-400', Customer: 'bg-green-400' }
const inr = v => `₹${Math.round(v || 0).toLocaleString('en-IN')}`
const ago = d => {
  if (!d) return 'no visits yet'
  const m = (Date.now() - new Date(String(d).replace(' ', 'T')).getTime()) / 60000
  if (m < 60) return `${Math.max(1, Math.round(m))} min ago`
  if (m < 60 * 48) return `${Math.round(m / 60)} h ago`
  return `${Math.round(m / 1440)} days ago`
}

// Sales pipeline: every lead in its lifecycle stage, worked out live from what the learner did.
// Drag a card to move it by hand (customers only come from purchases); "auto" puts it back.
export default function Pipeline() {
  const [data, setData] = useState(null)
  const [search, setSearch] = useState('')
  const [simulated, setSimulated] = useState(true)
  const [msg, setMsg] = useState('')
  const [over, setOver] = useState(null)
  const dragged = useRef(null)

  const load = () => getPipeline({ limit: 40, search, include_simulated: simulated })
    .then(r => setData(r.data)).catch(e => setMsg(e.response?.data?.detail || 'Could not load the pipeline'))

  useEffect(() => {
    const t = setTimeout(load, search ? 300 : 0)
    const poll = setInterval(load, 10000)              // live: new sign-ups and clicks move cards by themselves
    return () => { clearTimeout(t); clearInterval(poll) }
  }, [search, simulated])                              // eslint-disable-line react-hooks/exhaustive-deps

  async function drop(stage) {
    const card = dragged.current
    dragged.current = null
    setOver(null)
    if (!card || card.stage === stage) return
    if (stage === 'Customer') { setMsg('Customers come only from purchases — a card cannot be moved there by hand.'); return }
    if (card.stage === 'Customer') { setMsg('This person has bought — customers stay customers.'); return }
    try {
      await moveCard(card.user_id, { stage })
      setMsg(`${card.name} moved to ${stage} by hand. The CRM's own view is still shown on the card ("auto: ${card.auto_stage}").`)
      load()
    } catch (e) { setMsg(e.response?.data?.detail || 'Could not move the card') }
  }

  async function auto(card) {
    await resetCard(card.user_id).catch(() => {})
    setMsg(`${card.name} follows the CRM's stage again (${card.auto_stage}).`)
    load()
  }

  const cols = data?.columns || []
  const open = cols.filter(c => c.stage !== 'Customer')
  const totalValue = open.reduce((s, c) => s + (c.expected_value || 0), 0)

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-3 mb-2">
        <div>
          <h1 className="font-display text-2xl font-bold text-white">Pipeline</h1>
          <p className="text-slate-500 text-sm mt-1">
            Every lead in its stage — moved by what they do on the website, live. Drag a card to override; “auto” hands it back.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <input className="inp w-56 py-2" placeholder="Search name or email" value={search} onChange={e => setSearch(e.target.value)} />
          <label className="flex items-center gap-2 text-xs text-slate-400 bg-white/5 border border-white/10 rounded-xl px-3 py-2 cursor-pointer">
            <input type="checkbox" checked={simulated} onChange={e => setSimulated(e.target.checked)} /> simulated history
          </label>
        </div>
      </div>
      {data && (
        <p className="text-slate-400 text-xs mb-4">
          Open pipeline: <span className="text-white font-semibold">{inr(totalValue)}</span> expected within 14 days if we do nothing
          (each lead's score × course price) · updated {ago(data.generated_at)}
        </p>
      )}
      {msg && <p className="text-sm text-sky-accent mb-3">{msg}</p>}
      {!data ? <div className="card p-10 text-center text-slate-500">Loading…</div> : (
        <div className="grid gap-3" style={{ gridTemplateColumns: `repeat(${cols.length}, minmax(210px, 1fr))`, overflowX: 'auto' }}>
          {cols.map(col => (
            <div key={col.stage}
              onDragOver={e => { e.preventDefault(); setOver(col.stage) }}
              onDragLeave={() => setOver(o => (o === col.stage ? null : o))}
              onDrop={() => drop(col.stage)}
              className={`rounded-2xl border bg-white/[0.02] p-2 min-h-[300px] transition-colors ${over === col.stage ? 'border-sky-accent bg-sky-500/5' : 'border-white/10'}`}>
              <div className="px-2 pt-1 pb-2">
                <div className="flex items-center justify-between">
                  <p className="font-display font-semibold text-white text-sm flex items-center gap-2">
                    <span className={`w-2 h-2 rounded-full ${STAGE_DOT[col.stage]}`} />{col.stage}
                  </p>
                  <span className="text-xs text-slate-400">{col.count.toLocaleString()}</span>
                </div>
                <p className="text-[10px] text-slate-500 leading-snug mt-1" title={col.about}>{col.about}</p>
                {col.stage !== 'Customer'
                  ? <p className="text-[11px] text-slate-400 mt-1">{inr(col.expected_value)} expected</p>
                  : <p className="text-[11px] text-slate-400 mt-1">bought</p>}
              </div>
              <div className="space-y-2 max-h-[68vh] overflow-y-auto pr-1">
                {col.cards.map(c => (
                  <div key={c.user_id} draggable={c.stage !== 'Customer'}
                    onDragStart={() => { dragged.current = c }}
                    className={`bg-[#0B1426] border-l-2 ${STAGE_COLOR[c.stage]} border border-white/10 rounded-xl p-3 cursor-grab active:cursor-grabbing`}>
                    <div className="flex items-start justify-between gap-2">
                      <Link to={`/leads/${c.lead_id}`} className="text-white text-sm font-semibold hover:underline leading-tight">{c.name}</Link>
                      <span className="text-xs font-mono text-white bg-white/10 rounded px-1.5">{Math.round(c.score)}</span>
                    </div>
                    <p className="text-[11px] text-slate-500 truncate">{c.course || '—'}</p>
                    <div className="flex flex-wrap gap-1 mt-2">
                      {c.simulated && <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-slate-500">simulated</span>}
                      {c.control_group && <span className="text-[9px] px-1.5 py-0.5 rounded bg-violet-500/10 text-violet-300" title="5% of leads the CRM never contacts automatically: its honest check">control group</span>}
                      {c.moved_by_hand && <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300" title={c.override_note || ''}>moved by hand · auto: {c.auto_stage}</span>}
                    </div>
                    <p className="text-[10px] text-slate-500 mt-2">
                      Last seen {ago(c.last_seen)}{c.last_action_label ? ` · last step: ${c.last_action_label.toLowerCase()}` : ''}
                    </p>
                    {c.expected_value != null && c.stage !== 'Customer' && <p className="text-[10px] text-slate-400">{inr(c.expected_value)} expected</p>}
                    {c.moved_by_hand && <button onClick={() => auto(c)} className="text-[10px] text-sky-accent hover:underline mt-1">auto</button>}
                  </div>
                ))}
                {col.count > col.cards.length && (
                  <p className="text-[11px] text-slate-500 text-center py-2">+ {(col.count - col.cards.length).toLocaleString()} more (search to find one)</p>
                )}
                {col.count === 0 && <p className="text-[11px] text-slate-600 text-center py-6">Nobody here yet</p>}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
