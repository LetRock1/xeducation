import { useState } from 'react'
import { tracker } from '../utils/tracker'
const RESPONSES = [
  "Hi! I'm Priya, your X Education advisor. How can I help you today?",
  "Great question! Our courses are designed for working professionals who want real career growth. Which course interests you most?",
  "Our programmes include live mentorship, industry projects, and placement support. Would you like to book a free counselling session?",
  "You can sign up in under 2 minutes! Click 'Get Started' at the top and our team will reach out within 2 hours.",
]
export default function ChatWidget() {
  const [open,    setOpen]  = useState(false)
  const [msgs,    setMsgs]  = useState([{ from:'bot', text: RESPONSES[0] }])
  const [input,   setInput] = useState('')
  const [tracked, setTracked] = useState(false)
  function handleOpen() { setOpen(true); if (!tracked) { tracker.chat(); setTracked(true) } }
  function send() {
    if (!input.trim()) return
    const bot = RESPONSES[Math.min(msgs.length, RESPONSES.length-1)]
    setMsgs(p => [...p, { from:'user', text: input }, { from:'bot', text: bot }])
    setInput('')
  }
  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-3">
      {open && (
        <div className="w-80 bg-white rounded-2xl shadow-2xl border border-slate-200 overflow-hidden">
          <div className="bg-navy px-4 py-3 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-8 h-8 rounded-full bg-gradient-to-br from-sky-accent to-gold flex items-center justify-center text-navy font-bold text-sm">P</div>
              <div>
                <p className="text-white text-sm font-semibold font-display">Priya — Advisor</p>
                <p className="text-green-400 text-xs flex items-center gap-1"><span className="w-1.5 h-1.5 bg-green-400 rounded-full inline-block"/>Online now</p>
              </div>
            </div>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-white text-xl leading-none">×</button>
          </div>
          <div className="h-56 overflow-y-auto px-4 py-3 space-y-3 bg-slate-50">
            {msgs.map((m,i) => (
              <div key={i} className={`flex ${m.from==='user'?'justify-end':'justify-start'}`}>
                <div className={`max-w-[80%] text-sm px-3 py-2 rounded-xl leading-relaxed
                  ${m.from==='user'?'bg-ember text-white rounded-br-none':'bg-white text-slate-700 border border-slate-200 rounded-bl-none shadow-sm'}`}>
                  {m.text}
                </div>
              </div>
            ))}
          </div>
          <div className="px-3 py-3 border-t border-slate-200 flex gap-2">
            <input value={input} onChange={e=>setInput(e.target.value)} onKeyDown={e=>e.key==='Enter'&&send()} placeholder="Type a message…" className="flex-1 text-sm border border-slate-200 rounded-lg px-3 py-2 focus:outline-none focus:border-sky-accent"/>
            <button onClick={send} className="bg-ember text-white px-3 py-2 rounded-lg text-sm hover:bg-orange-600 transition">→</button>
          </div>
        </div>
      )}
      <button onClick={handleOpen} className="w-14 h-14 rounded-full bg-gradient-to-br from-ember to-gold shadow-xl flex items-center justify-center text-white text-2xl hover:scale-110 transition-transform">
        {open ? '×' : '💬'}
      </button>
    </div>
  )
}
