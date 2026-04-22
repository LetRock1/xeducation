import { useState, useEffect } from 'react'
import { getReviews, addReview } from '../utils/api'
import { useAuth } from '../context/AuthContext'

export default function ReviewSection({ courseSlug }) {
  const { user } = useAuth()
  const [reviews, setReviews] = useState([])
  const [rating,  setRating]  = useState(0)
  const [text,    setText]    = useState('')
  const [submitting, setSub]  = useState(false)
  const [msg, setMsg]         = useState('')

  useEffect(() => { getReviews(courseSlug).then(r => setReviews(r.data.reviews)).catch(() => {}) }, [courseSlug])

  async function submit() {
    if (!rating) { setMsg('Please select a rating.'); return }
    setSub(true); setMsg('')
    try {
      await addReview({ course_slug: courseSlug, rating, review_text: text })
      setMsg('✅ Review submitted!'); setRating(0); setText('')
      getReviews(courseSlug).then(r => setReviews(r.data.reviews))
    } catch(e) { setMsg('❌ ' + (e.response?.data?.detail || 'Error')) }
    finally { setSub(false) }
  }

  const avg = reviews.length ? (reviews.reduce((s,r)=>s+r.rating,0)/reviews.length).toFixed(1) : null

  return (
    <div className="max-w-3xl mx-auto px-6 py-10">
      <h2 className="font-display text-2xl font-bold text-navy mb-2">Student Reviews</h2>
      {avg && <p className="text-slate-500 text-sm mb-6">⭐ {avg}/5 · {reviews.length} review{reviews.length!==1?'s':''}</p>}

      {user && (
        <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-8">
          <p className="font-semibold text-navy text-sm mb-3">Rate this course</p>
          <div className="flex gap-2 mb-4">
            {[1,2,3,4,5].map(s => (
              <button key={s} onClick={() => setRating(s)}
                className={`text-3xl transition-transform hover:scale-110 ${s<=rating?'text-gold':'text-slate-200'}`}>★</button>
            ))}
          </div>
          <textarea value={text} onChange={e=>setText(e.target.value)} rows={3}
            placeholder="Share your experience (optional)…"
            className="inp mb-3"/>
          {msg && <p className="text-sm mb-3">{msg}</p>}
          <button onClick={submit} disabled={submitting} className="btn-primary text-sm">
            {submitting ? 'Submitting…' : 'Submit Review'}
          </button>
        </div>
      )}

      {reviews.length === 0
        ? <p className="text-slate-400 text-sm text-center py-8">No reviews yet. Be the first to review this course!</p>
        : <div className="space-y-4">
            {reviews.map(r => (
              <div key={r.id} className="bg-white border border-slate-200 rounded-xl p-5">
                <div className="flex items-center justify-between mb-2">
                  <p className="font-semibold text-navy text-sm">{r.name}</p>
                  <p className="text-gold text-sm">{'★'.repeat(r.rating)}{'☆'.repeat(5-r.rating)}</p>
                </div>
                {r.review_text && <p className="text-slate-600 text-sm leading-relaxed italic">"{r.review_text}"</p>}
                <p className="text-slate-400 text-xs mt-2">{new Date(r.created_at).toLocaleDateString('en-IN')}</p>
              </div>
            ))}
          </div>
      }
    </div>
  )
}
