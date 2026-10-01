import { useEffect, useState } from 'react'
import { getUnansweredQnA, answerQnA } from '../utils/api'

export default function QnAPage() {
  const [questions, setQs]      = useState([])
  const [loading,   setLoading] = useState(true)
  const [answers,   setAnswers] = useState({})   // { [qid]: text }
  const [sending,   setSending] = useState({})   // { [qid]: bool }
  const [results,   setResults] = useState({})   // { [qid]: message }

  const load = () => {
    setLoading(true)
    getUnansweredQnA()
      .then(r => setQs(r.data.questions))
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const setAns = (id, val) => setAnswers(p => ({ ...p, [id]: val }))

  async function publish(qid) {
    if (!answers[qid]?.trim()) return
    setSending(p => ({ ...p, [qid]: true }))
    try {
      await answerQnA({ qna_id: qid, answer: answers[qid] })
      setResults(p => ({ ...p, [qid]: 'Done Answer published!' }))
      setTimeout(() => load(), 1200)
    } catch {
      setResults(p => ({ ...p, [qid]: 'Error Failed to publish. Try again.' }))
    } finally {
      setSending(p => ({ ...p, [qid]: false }))
    }
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="font-display text-2xl font-bold text-white">
          Unanswered Questions
        </h1>
        {!loading && (
          <span className="text-slate-500 text-sm">
            {questions.length} question{questions.length !== 1 ? 's' : ''} waiting
          </span>
        )}
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20">
          <div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin" />
        </div>
      ) : !questions.length ? (
        <div className="card p-16 text-center">
          <p className="text-4xl mb-3">Great!</p>
          <p className="text-white font-display font-bold text-lg mb-1">All caught up!</p>
          <p className="text-slate-500 text-sm">Every question has been answered.</p>
        </div>
      ) : (
        <div className="space-y-5">
          {questions.map(q => (
            <div key={q.id} className="card p-6">
              {/* Header */}
              <div className="flex items-center gap-3 mb-4">
                <div className="w-9 h-9 rounded-full bg-white/10 flex items-center
                                justify-center text-sky-accent text-sm font-bold flex-shrink-0">
                  {q.user_name?.[0]?.toUpperCase() || '?'}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-white font-semibold text-sm">{q.user_name}</p>
                  <p className="text-slate-500 text-xs">
                    Course: <span className="text-slate-400">{q.course_slug}</span>
                    {' · '}
                    {q.created_at?.slice(0, 10)}
                  </p>
                </div>
              </div>

              {/* Question */}
              <div className="bg-white/5 border border-white/10 rounded-xl px-4 py-3 mb-4">
                <p className="text-slate-300 text-sm leading-relaxed">
                   {q.question}
                </p>
              </div>

              {/* Answer input */}
              <textarea
                value={answers[q.id] || ''}
                onChange={e => setAns(q.id, e.target.value)}
                rows={3}
                placeholder="Type your expert answer here…"
                className="inp mb-3 text-sm"
              />

              {results[q.id] && (
                <p className={`text-sm mb-3 px-3 py-2 rounded-xl border ${
                  results[q.id].startsWith('Done')
                    ? 'text-green-400 bg-green-900/20 border-green-800/30'
                    : 'text-red-400 bg-red-900/20 border-red-800/30'}`}>
                  {results[q.id]}
                </p>
              )}

              <button
                onClick={() => publish(q.id)}
                disabled={sending[q.id] || !answers[q.id]?.trim()}
                className="btn text-sm disabled:opacity-50">
                {sending[q.id] ? '⏳ Publishing…' : 'Done Publish Answer'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}