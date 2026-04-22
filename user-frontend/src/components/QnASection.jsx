import { useState, useEffect } from 'react'
import { getQnA, askQuestion } from '../utils/api'
import { useAuth } from '../context/AuthContext'

export default function QnASection({ courseSlug }) {
  const { user } = useAuth()
  const [questions, setQs]  = useState([])
  const [question,  setQ]   = useState('')
  const [busy,      setBusy]= useState(false)
  const [msg,       setMsg] = useState('')

  useEffect(() => { getQnA(courseSlug).then(r => setQs(r.data.questions)).catch(() => {}) }, [courseSlug])

  async function submit() {
    if (!question.trim()) return
    setBusy(true); setMsg('')
    try {
      await askQuestion({ course_slug: courseSlug, question })
      setMsg('✅ Question submitted! Our team will answer shortly.')
      setQ('')
      getQnA(courseSlug).then(r => setQs(r.data.questions))
    } catch(e) { setMsg('❌ ' + (e.response?.data?.detail || 'Error')) }
    finally { setBusy(false) }
  }

  return (
    <div className="max-w-3xl mx-auto px-6 py-10 border-t border-slate-200">
      <h2 className="font-display text-2xl font-bold text-navy mb-6">Questions & Answers</h2>

      {user && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-8">
          <p className="font-semibold text-navy text-sm mb-3">Ask a question about this course</p>
          <textarea value={question} onChange={e=>setQ(e.target.value)} rows={2}
            placeholder="What would you like to know?…"
            className="inp mb-3"/>
          {msg && <p className="text-sm mb-3">{msg}</p>}
          <button onClick={submit} disabled={busy} className="btn-primary text-sm">
            {busy ? 'Submitting…' : 'Ask Question'}
          </button>
        </div>
      )}

      {questions.length === 0
        ? <p className="text-slate-400 text-sm text-center py-6">No questions yet.</p>
        : <div className="space-y-5">
            {questions.map(q => (
              <div key={q.id} className="bg-slate-50 border border-slate-200 rounded-xl p-5">
                <p className="font-semibold text-slate-700 text-sm mb-1">🙋 {q.user_name}</p>
                <p className="text-slate-700 text-sm mb-3">{q.question}</p>
                {q.answer
                  ? <div className="bg-blue-50 border border-blue-100 rounded-lg px-4 py-3">
                      <p className="text-blue-700 text-xs font-semibold mb-1">✅ {q.answered_by}</p>
                      <p className="text-slate-700 text-sm">{q.answer}</p>
                    </div>
                  : <p className="text-slate-400 text-xs italic">Awaiting answer from X Education Team…</p>
                }
              </div>
            ))}
          </div>
      }
    </div>
  )
}
