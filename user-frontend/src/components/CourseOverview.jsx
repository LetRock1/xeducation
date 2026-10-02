import { useEffect, useRef, useState } from 'react'

// A short, auto-playing course overview built from the course data (5 slides,
// ~35 s). It counts as "video watched" for the lead score only once at least
// half of it has actually played — not just because the play button was clicked.
const SLIDE_MS = 7000

export default function CourseOverview({ course, onClose, onHalfWatched }) {
  const slides = [
    { h: course.title, b: <p className="text-lg text-slate-300">{course.tagline}</p> },
    { h: "What you'll gain", b: <ul className="space-y-2">{course.outcomes.map(o => <li key={o}>✓ {o}</li>)}</ul> },
    { h: 'How the programme runs', b: <ol className="space-y-1.5 text-sm">{course.curriculum.map(m => <li key={m.w}><b className="text-gold">{m.w}</b> — {m.t}</li>)}</ol> },
    { h: 'Learn from', b: <div><p className="text-xl font-bold">{course.instructor.name}</p><p className="text-slate-300">{course.instructor.role} · {course.instructor.exp}</p></div> },
    { h: 'Duration & fees', b: <p className="text-lg">{course.duration} · {course.level}<br />₹{course.price.toLocaleString()} or ₹{course.emi.toLocaleString()}/month EMI</p> },
  ]
  const total = slides.length * SLIDE_MS
  const [elapsed, setElapsed] = useState(0)
  const [playing, setPlaying] = useState(true)
  const reported = useRef(false)

  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => setElapsed(e => Math.min(e + 250, total)), 250)
    return () => clearInterval(t)
  }, [playing, total])

  useEffect(() => {
    if (!reported.current && elapsed >= total / 2) { reported.current = true; onHalfWatched?.() }
    if (elapsed >= total) setPlaying(false)
  }, [elapsed, total, onHalfWatched])

  const idx = Math.min(Math.floor(elapsed / SLIDE_MS), slides.length - 1)
  const s = slides[idx]
  return (
    <div className="fixed inset-0 z-[60] bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div className="w-full max-w-2xl bg-navy rounded-2xl overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
        <div className={`aspect-video relative p-10 text-white flex flex-col justify-center bg-gradient-to-br ${course.color}`}>
          <div className="absolute inset-0 bg-navy/80" />
          <div className="relative">
            <p className="text-sky-accent text-xs font-bold tracking-widest mb-3">COURSE OVERVIEW · {idx + 1}/{slides.length}</p>
            <h3 className="font-display text-3xl font-extrabold mb-4">{s.h}</h3>
            <div className="text-slate-100">{s.b}</div>
          </div>
        </div>
        <div className="px-5 py-3 flex items-center gap-4">
          <button onClick={() => elapsed >= total ? (setElapsed(0), setPlaying(true)) : setPlaying(p => !p)}
            className="text-white text-sm font-semibold w-16">{elapsed >= total ? 'Replay' : playing ? 'Pause' : 'Play'}</button>
          <div className="flex-1 h-1.5 bg-white/20 rounded-full overflow-hidden">
            <div className="h-full bg-sky-accent transition-all" style={{ width: `${(elapsed / total) * 100}%` }} />
          </div>
          <span className="text-slate-400 text-xs w-12 text-right">{Math.round(elapsed / 1000)}s/{total / 1000}s</span>
          <button onClick={onClose} className="text-slate-400 hover:text-white text-xl leading-none">×</button>
        </div>
      </div>
    </div>
  )
}
