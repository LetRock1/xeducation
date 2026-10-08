import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getActions, completeAction, whatsappLink } from '../utils/api'

const fmt = d => d ? new Date(String(d).replace(' ', 'T')).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '—'

// Calls and WhatsApp messages the next-best-action engine decided are worth doing,
// ranked by expected extra profit. Marking an outcome feeds the closed loop.
export default function Actions() {
  const [status, setStatus] = useState('open')
  const [segment, setSegment] = useState('all')
  const [rows, setRows] = useState([])
  const [other, setOther] = useState(0)
  const [msg, setMsg] = useState('')
  const load = () => getActions(status, segment).then(r => { setRows(r.data.actions); setOther(r.data.other_segment_count || 0) }).catch(() => {})
  useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t) }, [status, segment])   // eslint-disable-line react-hooks/exhaustive-deps

  async function done(id, outcome) {
    await completeAction(id, outcome).catch(() => {}); load()
  }
  async function openWa(t) {
    try {
      const r = await whatsappLink({ lead_id: t.lead_id, message: t.detail || '' })
      window.open(r.data.url, '_blank', 'noopener'); setMsg('WhatsApp opened — press send, then mark it as sent.')
    } catch (e) { setMsg(e.response?.data?.detail || 'Could not open WhatsApp') }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h1 className="font-display text-2xl font-bold text-white">Today's actions</h1>
        <div className="flex gap-2">
          {['open', 'done', 'all'].map(s => (
            <button key={s} onClick={() => setStatus(s)}
              className={`px-4 py-2 rounded-xl text-sm capitalize ${status === s ? 'bg-ember text-white' : 'bg-white/5 border border-white/10 text-slate-400'}`}>{s}</button>
          ))}
        </div>
      </div>
      <p className="text-slate-500 text-sm mb-3">Chosen by the next-best-action model: people for whom a call or WhatsApp is expected to change the outcome enough to be worth the time — highest expected gain first.
        The CRM decides who to call and why; an advisor makes the call and records the result here, which the learning loop uses.
        Tasks of simulated learners (fake numbers) are done by the simulated advisor 1–24 h later, unless you record them first.</p>
      <div className="flex items-center gap-2 mb-6">
        {[['all', 'Everyone'], ['real', 'Signed up themselves'], ['simulated', 'Simulated']].map(([k, label]) => (
          <button key={k} onClick={() => setSegment(k)}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold ${segment === k ? 'bg-sky-500/20 border border-sky-500/50 text-sky-200' : 'bg-white/5 border border-white/10 text-slate-400'}`}>{label}</button>
        ))}
        {segment !== 'all' && other > 0 && <span className="text-[11px] text-slate-500">{other} other task(s) not shown</span>}
      </div>
      {msg && <p className="text-sm text-sky-accent mb-4">{msg}</p>}
      {!rows.length ? <div className="card p-10 text-center text-slate-500">No {status === 'all' ? '' : status} actions{segment === 'real' ? ' for people who signed up themselves yet' : ''}.
        <span className="block text-xs mt-2">A call task appears when the CRM decides a call is worth it for a learner who gave a phone number (or when you press “Do it now” on a lead).</span></div> : (
        <div className="space-y-3">
          {rows.map(t => (
            <div key={t.id} className="card p-5">
              <div className="flex flex-wrap items-start gap-4">
                <div className="flex-1 min-w-[240px]">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-slate-300 uppercase">{t.task_type}</span>
                    <p className="text-white font-semibold">{t.title}</p>
                    {t.simulated && <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/10 text-slate-400" title="Simulated learner: the number is not real. The simulated advisor does this task 1–24 h after it was created, unless you record an outcome first (that outcome is used).">simulated</span>}
                    {t.policy === 'explore' && <span className="text-[10px] px-2 py-0.5 rounded-full border border-violet-500/40 text-violet-300" title="15% of decisions are picked at random so the CRM keeps learning what works">random pick (learning sample)</span>}
                    {t.policy === 'manual' && <span className="text-[10px] px-2 py-0.5 rounded-full border border-ember/40 text-ember">added by hand</span>}
                  </div>
                  <p className="text-slate-400 text-xs mt-1">{t.email} · {t.phone ? <a href={`tel:${t.phone.replace(/\s/g, '')}`} className="text-sky-accent hover:underline">{t.phone}</a> : 'no phone'} · score {Math.round(t.lead_score || 0)} · {fmt(t.created_at)}</p>
                  {t.detail && <p className="text-slate-300 text-sm mt-3 leading-relaxed">{t.detail}</p>}
                  {t.tips?.length > 0 && (
                    <p className="text-slate-500 text-xs mt-2">How to move them up: <span className="text-slate-300">{t.tips[0].title}</span> ({t.tips[0].detail})</p>
                  )}
                </div>
                <div className="text-right">
                  <p className="text-green-400 font-display font-bold">+₹{Math.round(t.expected_gain || 0).toLocaleString()}</p>
                  <p className="text-slate-500 text-[11px]">expected extra profit</p>
                  {t.lead_id && <Link to={`/leads/${t.lead_id}`} className="text-sky-accent text-xs hover:underline block mt-2">Open lead</Link>}
                </div>
              </div>
              {t.status === 'open' ? (
                <div className="flex flex-wrap gap-2 mt-4">
                  {t.task_type === 'whatsapp' && <button onClick={() => openWa(t)} className="btn text-xs py-1.5 px-3">Open WhatsApp</button>}
                  {t.task_type === 'whatsapp'
                    ? <button onClick={() => done(t.id, 'sent')} className="text-xs border border-white/15 text-slate-300 rounded-lg px-3 py-1.5">Mark sent</button>
                    : ['reached', 'no_answer', 'not_interested'].map(o => (
                        <button key={o} onClick={() => done(t.id, o)} className="text-xs border border-white/15 text-slate-300 rounded-lg px-3 py-1.5 hover:border-white/40">
                          {o === 'reached' ? 'Spoke to them' : o === 'no_answer' ? 'No answer' : 'Not interested'}
                        </button>))}
                </div>
              ) : <p className="text-xs text-slate-500 mt-3">Done · {({ reached: 'spoke to them', no_answer: 'no answer', not_interested: 'not interested', sent: 'sent' })[t.outcome] || t.outcome} · {fmt(t.done_at)}{t.done_by === 'simulated advisor' ? ' · by the simulated advisor' : t.done_by === 'team' ? ' · by the team' : ''}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
