import { useEffect, useRef, useState } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { sendChat, requestCallback } from '../utils/api'
import { useAuth } from '../context/AuthContext'
import { tracker } from '../utils/tracker'

// Website assistant. It is clearly labelled as automated, answers only from the
// course catalogue + FAQ (user-backend/assistant.py), and can book a real
// callback with an advisor. Transcripts are visible to the sales team.
const GREETING = {
  from: 'bot',
  text: "Hi! I'm the X Education assistant (automated). Ask me about fees, duration, syllabus or instructors — or I can find the right course for you, or arrange a call with an advisor.",
  suggestions: ['What are the fees?', 'Which course suits me?', 'How long is it?', 'Talk to an advisor'],
}

function CallbackForm({ courseSlug, defaultPhone, onDone }) {
  const [phone, setPhone] = useState(defaultPhone || '')
  const [time, setTime] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')
  async function submit(e) {
    e.preventDefault(); setBusy(true); setErr('')
    try {
      const r = await requestCallback({ phone, preferred_time: time, course_slug: courseSlug })
      onDone(r.data.message)
    } catch (e) { setErr(e.response?.data?.detail || 'Could not book the callback') }
    finally { setBusy(false) }
  }
  return (
    <form onSubmit={submit} className="bg-white border border-slate-200 rounded-xl p-3 space-y-2 text-sm">
      <input required value={phone} onChange={e => setPhone(e.target.value)} placeholder="Phone, e.g. +91 98xxxxxxxx"
        className="w-full border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:border-sky-accent" />
      <input value={time} onChange={e => setTime(e.target.value)} placeholder="Best time (e.g. weekdays after 6 pm)"
        className="w-full border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:border-sky-accent" />
      {err && <p className="text-red-500 text-xs">{err}</p>}
      <button disabled={busy} className="w-full bg-ember text-white rounded-lg py-2 font-semibold disabled:opacity-60">
        {busy ? 'Booking…' : 'Request callback'}
      </button>
    </form>
  )
}

export default function ChatWidget() {
  const { user, profile } = useAuth()
  const location = useLocation()
  const courseSlug = (location.pathname.match(/^\/courses\/([^/]+)/) || [])[1] || null
  const [open, setOpen] = useState(false)
  const [msgs, setMsgs] = useState([GREETING])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [initiated, setInitiated] = useState(false)
  const endRef = useRef(null)

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [msgs, open])

  function conversationId() {
    try { return sessionStorage.getItem('xe_chat_id') } catch { return null }
  }

  async function send(text) {
    const message = (text ?? input).trim()
    if (!message || busy) return
    setInput('')
    setMsgs(m => [...m, { from: 'user', text: message }])
    if (!initiated) { tracker.chat(); setInitiated(true) }   // ChatInitiated = started a conversation
    setBusy(true)
    try {
      const r = await sendChat({ message, conversation_id: conversationId(), course_slug: courseSlug })
      try { sessionStorage.setItem('xe_chat_id', r.data.conversation_id) } catch { /* ignore */ }
      setMsgs(m => [...m, { from: 'bot', text: r.data.reply, links: r.data.links, suggestions: r.data.suggestions, action: r.data.action }])
    } catch {
      setMsgs(m => [...m, { from: 'bot', text: "Sorry, I couldn't reach the server. Please try again in a moment." }])
    } finally { setBusy(false) }
  }

  const last = msgs[msgs.length - 1]
  return (
    <div className="no-print fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {open && (
        <div className="w-80 sm:w-96 bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
          <div className="bg-navy px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-accent to-gold flex items-center justify-center text-navy font-bold text-sm">X</div>
              <div>
                <p className="text-white text-sm font-semibold font-display">X Education Assistant</p>
                <p className="text-slate-400 text-xs">Automated · answers from our course catalogue</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-white text-xl leading-none" aria-label="Close chat">×</button>
          </div>
          <div className="h-80 overflow-y-auto px-4 py-3 space-y-3 bg-slate-50">
            {msgs.map((m, i) => (
              <div key={i} className={`flex flex-col ${m.from === 'user' ? 'items-end' : 'items-start'}`}>
                <div className={`max-w-[85%] text-sm px-3 py-2 rounded-xl leading-relaxed whitespace-pre-line
                  ${m.from === 'user' ? 'bg-ember text-white rounded-br-none' : 'bg-white text-slate-700 border border-slate-200 rounded-bl-none shadow-sm'}`}>
                  {m.text}
                </div>
                {m.links?.length > 0 && (
                  <div className="flex flex-wrap gap-1.5 mt-1.5">
                    {m.links.map(l => (
                      <Link key={l.to + l.label} to={l.to} onClick={() => setOpen(false)}
                        className="text-xs bg-sky-accent/10 text-navy border border-sky-accent/40 rounded-full px-2.5 py-1 hover:bg-sky-accent/20">{l.label} →</Link>
                    ))}
                  </div>
                )}
                {m.action?.type === 'callback_form' && i === msgs.length - 1 && (
                  <div className="w-full mt-2">
                    <CallbackForm courseSlug={courseSlug} defaultPhone={profile?.phone}
                      onDone={text => setMsgs(ms => [...ms, { from: 'bot', text: '✅ ' + text }])} />
                  </div>
                )}
              </div>
            ))}
            {busy && <div className="text-slate-400 text-xs">Assistant is typing…</div>}
            <div ref={endRef} />
          </div>
          {last?.suggestions?.length > 0 && !busy && (
            <div className="px-3 pt-2 flex flex-wrap gap-1.5 bg-white">
              {last.suggestions.map(s => (
                <button key={s} onClick={() => send(s)}
                  className="text-xs border border-slate-200 rounded-full px-2.5 py-1 text-slate-600 hover:border-sky-accent hover:text-navy">{s}</button>
              ))}
            </div>
          )}
          <div className="px-3 py-3 flex gap-2 bg-white">
            <input value={input} onChange={e => setInput(e.target.value)} onKeyDown={e => e.key === 'Enter' && send()}
              placeholder={user ? 'Ask about fees, syllabus, duration…' : 'Ask anything about our courses…'}
              className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:border-sky-accent" />
            <button onClick={() => send()} disabled={busy} className="bg-ember text-white px-3 py-2 rounded-lg text-sm hover:bg-orange-600 transition disabled:opacity-60">→</button>
          </div>
        </div>
      )}
      <button onClick={() => setOpen(o => !o)} aria-label="Open chat"
        className="w-14 h-14 rounded-full bg-gradient-to-br from-ember to-gold shadow-xl flex items-center justify-center text-white text-2xl hover:scale-110 transition-transform">
        {open ? '×' : '💬'}
      </button>
    </div>
  )
}
