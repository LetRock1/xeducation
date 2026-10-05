import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { askCopilot, getCopilotInfo } from '../utils/api'

// "Ask the CRM": answers come only from live data (each answer shows which data it read);
// drafts are never sent by the Copilot — a person opens them and decides.
export default function Copilot() {
  const [info, setInfo] = useState(null)
  const [q, setQ] = useState('')
  const [chat, setChat] = useState([])
  const [busy, setBusy] = useState(false)
  const end = useRef(null)
  const navigate = useNavigate()

  useEffect(() => { getCopilotInfo().then(r => setInfo(r.data)).catch(() => {}) }, [])
  useEffect(() => { end.current?.scrollIntoView({ behavior: 'smooth' }) }, [chat])

  async function ask(question) {
    const text = (question ?? q).trim()
    if (!text || busy) return
    setQ(''); setBusy(true)
    setChat(c => [...c, { role: 'user', text }])
    try {
      const r = await askCopilot(text)
      setChat(c => [...c, { role: 'bot', ...r.data }])
    } catch (e) {
      setChat(c => [...c, { role: 'bot', answer: e.response?.data?.detail || 'Could not answer right now.', tools: [], drafts: [], links: [] }])
    } finally { setBusy(false) }
  }

  const copy = d => navigator.clipboard?.writeText(`Subject: ${d.subject}\n\n${d.body}`)

  return (
    <div className="max-w-4xl">
      <h1 className="font-display text-2xl font-bold text-white">Ask the CRM</h1>
      <p className="text-slate-500 text-sm mt-1 mb-4">
        Plain-English questions, answered only from the CRM's live data — every answer shows what it read.
        It can draft emails and A/B tests; it never sends anything. {info && (info.gemini
          ? 'Gemini helps it understand freer wording (it is never the source of a number).'
          : 'Runs without an AI key: it understands the kinds of questions below; add GEMINI_API_KEY for freer wording.')}
      </p>

      <div className="card p-4 min-h-[380px] max-h-[62vh] overflow-y-auto space-y-4">
        {!chat.length && (
          <div className="text-slate-500 text-sm py-6 text-center">Try one of these:</div>
        )}
        {!chat.length && (
          <div className="flex flex-wrap gap-2 justify-center">
            {(info?.suggestions || []).map(s => (
              <button key={s} onClick={() => ask(s)} className="text-xs border border-white/15 text-slate-300 rounded-full px-3 py-1.5 hover:border-sky-accent hover:text-white">{s}</button>
            ))}
          </div>
        )}
        {chat.map((m, i) => m.role === 'user' ? (
          <div key={i} className="flex justify-end"><p className="bg-ember/20 border border-ember/30 text-white text-sm rounded-2xl rounded-br-sm px-4 py-2 max-w-[80%]">{m.text}</p></div>
        ) : (
          <div key={i} className="flex">
            <div className="bg-white/5 border border-white/10 rounded-2xl rounded-bl-sm px-4 py-3 max-w-[92%]">
              <p className="text-slate-100 text-sm whitespace-pre-line leading-relaxed">{m.answer}</p>
              {m.drafts?.map((d, j) => d.type === 'email' ? (
                <div key={j} className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
                  <p className="text-amber-300 text-[11px] font-semibold uppercase tracking-wide mb-1">Draft email — not sent</p>
                  <p className="text-white text-sm font-semibold">{d.subject}</p>
                  <p className="text-slate-300 text-xs whitespace-pre-line mt-1">{d.body}</p>
                  <div className="flex gap-2 mt-2">
                    <button onClick={() => copy(d)} className="text-xs border border-white/15 text-slate-300 rounded-lg px-3 py-1">Copy</button>
                    {d.lead_id && <Link to={`/leads/${d.lead_id}`} className="text-xs btn !py-1 !px-3">Open lead to edit & send</Link>}
                  </div>
                </div>
              ) : (
                <div key={j} className="mt-3 rounded-xl border border-amber-500/30 bg-amber-500/5 p-3">
                  <p className="text-amber-300 text-[11px] font-semibold uppercase tracking-wide mb-1">Draft A/B test — not created yet</p>
                  <p className="text-white text-sm font-semibold">{d.name}</p>
                  <p className="text-slate-400 text-xs">{d.variants.map(v => v.label).join(' vs ')}{d.control_share ? ` vs ${Math.round(d.control_share * 100)}% no-email control` : ''} · {d.metric === 'click' ? 'clicks' : 'purchases'} · {d.tier}</p>
                  <button onClick={() => navigate('/ab-tests', { state: { draft: d } })} className="text-xs btn !py-1 !px-3 mt-2">Open in A/B tests to review</button>
                </div>
              ))}
              {m.links?.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-3">
                  {m.links.map((l, j) => l.type === 'lead'
                    ? <Link key={j} to={`/leads/${l.lead_id}`} className="text-[11px] text-sky-accent border border-sky-500/30 rounded-full px-2.5 py-1 hover:bg-sky-500/10">{l.label}</Link>
                    : <Link key={j} to={l.to} className="text-[11px] text-sky-accent border border-sky-500/30 rounded-full px-2.5 py-1 hover:bg-sky-500/10">{l.label}</Link>)}
                </div>
              )}
              {m.tools?.length > 0 && (
                <details className="mt-3">
                  <summary className="text-[11px] text-slate-500 cursor-pointer select-none">How I got this{m.used_gemini ? ' · wording by Gemini, numbers checked' : ''}</summary>
                  {m.tools.map((t, j) => (
                    <div key={j} className="text-[11px] text-slate-400 mt-1">
                      <p>Tool <span className="text-slate-200">{t.name}</span>: {t.about}. Read from {t.source} at {t.read_at}.</p>
                      <pre className="mt-1 bg-[#060D1A] border border-white/10 rounded-lg p-2 overflow-x-auto text-[10px] text-slate-400 max-h-40">{JSON.stringify(t.data, null, 1)}</pre>
                    </div>
                  ))}
                </details>
              )}
            </div>
          </div>
        ))}
        {busy && <p className="text-slate-500 text-xs">Reading the data…</p>}
        <div ref={end} />
      </div>

      <form onSubmit={e => { e.preventDefault(); ask() }} className="flex gap-2 mt-3">
        <input value={q} onChange={e => setQ(e.target.value)} className="inp" placeholder="Ask about leads, calls, the pipeline, A/B tests, the learning loop, revenue…" />
        <button type="submit" disabled={busy || !q.trim()} className="btn whitespace-nowrap">Ask</button>
      </form>
      {chat.length > 0 && (
        <div className="flex flex-wrap gap-2 mt-3">
          {(info?.suggestions || []).slice(0, 5).map(s => (
            <button key={s} onClick={() => ask(s)} className="text-[11px] border border-white/10 text-slate-400 rounded-full px-2.5 py-1 hover:border-white/30 hover:text-white">{s}</button>
          ))}
        </div>
      )}
    </div>
  )
}
