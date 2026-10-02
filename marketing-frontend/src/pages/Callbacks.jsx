import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getCallbacks, closeCallback } from '../utils/api'

const fmt = d => d ? new Date(String(d).replace(' ', 'T')).toLocaleString('en-IN', { dateStyle: 'short', timeStyle: 'short' }) : '—'

// Callback requests made by learners in the website chat assistant.
export default function Callbacks() {
  const [status, setStatus] = useState('open')
  const [rows, setRows] = useState([])
  const load = () => getCallbacks(status).then(r => setRows(r.data.callbacks)).catch(() => {})
  useEffect(() => { load() }, [status])   // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-2xl font-bold text-white">Callback requests</h1>
        <div className="flex gap-2">
          {['open', 'done', 'all'].map(s => (
            <button key={s} onClick={() => setStatus(s)}
              className={`px-4 py-2 rounded-xl text-sm capitalize ${status === s ? 'bg-ember text-white' : 'bg-white/5 border border-white/10 text-slate-400'}`}>{s}</button>
          ))}
        </div>
      </div>
      <div className="card overflow-hidden">
        <table className="w-full text-sm">
          <thead><tr className="text-xs text-slate-500 uppercase tracking-wide border-b border-white/10">
            {['Person', 'Phone', 'Best time', 'Course', 'Requested', ''].map(h => <th key={h} className="px-4 py-3 text-left font-semibold">{h}</th>)}
          </tr></thead>
          <tbody className="divide-y divide-white/5">
            {!rows.length ? <tr><td colSpan={6} className="text-center py-12 text-slate-500">No {status === 'all' ? '' : status} callback requests.</td></tr> : rows.map(c => (
              <tr key={c.id}>
                <td className="px-4 py-3"><p className="text-white font-semibold">{c.name}</p><p className="text-slate-500 text-xs">{c.email}</p></td>
                <td className="px-4 py-3 text-slate-300">{c.phone}</td>
                <td className="px-4 py-3 text-slate-400 text-xs">{c.preferred_time || 'Any time'}</td>
                <td className="px-4 py-3 text-slate-400 text-xs">{c.course_slug || '—'}</td>
                <td className="px-4 py-3 text-slate-500 text-xs">{fmt(c.created_at)}</td>
                <td className="px-4 py-3 text-right space-x-3 whitespace-nowrap">
                  {c.lead_id && <Link to={`/leads/${c.lead_id}`} className="text-sky-accent text-xs hover:underline">Open lead</Link>}
                  {c.status === 'open'
                    ? <button onClick={async () => { await closeCallback(c.id).catch(() => {}); load() }} className="text-xs text-green-400 hover:underline">Mark called</button>
                    : <span className="text-xs text-slate-500">Done {fmt(c.closed_at)}</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
