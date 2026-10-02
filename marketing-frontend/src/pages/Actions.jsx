import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getActions, completeAction, whatsappLink } from '../utils/api'

const fmt = d => d ? new Date(String(d).replace(' ', 'T')).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '—'

// Calls and WhatsApp messages the next-best-action engine decided are worth doing,
// ranked by expected extra profit. Marking an outcome feeds the closed loop.
export default function Actions() {
  const [status, setStatus] = useState('open')
  const [rows, setRows] = useState([])
  const [msg, setMsg] = useState('')
  const load = () => getActions(status).then(r => setRows(r.data.actions)).catch(() => {})
  useEffect(() => { load() }, [status])   // eslint-disable-line react-hooks/exhaustive-deps

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
      <p className="text-slate-500 text-sm mb-6">Chosen by the next-best-action model: people for whom a call or WhatsApp is expected to change the outcome enough to be worth the time — highest expected gain first.</p>
      {msg && <p className="text-sm text-sky-accent mb-4">{msg}</p>}
      {!rows.length ? <div className="card p-10 text-center text-slate-500">No {status === 'all' ? '' : status} actions.</div> : (
        <div className="space-y-3">
          {rows.map(t => (
            <div key={t.id} className="card p-5">
              <div className="flex flex-wrap items-start gap-4">
                <div className="flex-1 min-w-[240px]">
                  <div className="flex items-center gap-2">
                    <span className="text-xs px-2 py-0.5 rounded-full bg-white/10 text-slate-300 uppercase">{t.task_type}</span>
                    <p className="text-white font-semibold">{t.title}</p>
                  </div>
                  <p className="text-slate-400 text-xs mt-1">{t.email} · {t.phone || 'no phone'} · score {Math.round(t.lead_score || 0)} · {fmt(t.created_at)}</p>
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
              ) : <p className="text-xs text-slate-500 mt-3">Done · {t.outcome} · {fmt(t.done_at)}</p>}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
