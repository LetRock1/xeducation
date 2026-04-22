import { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { submitEnquiry } from '../utils/api'
import { useAuth }       from '../context/AuthContext'
import { getCourseBySlug } from '../data/courses'

export default function Enquiry() {
  const { slug }   = useParams()
  const navigate   = useNavigate()
  const { user, profile } = useAuth()
  const course     = getCourseBySlug(slug)
  const [phone,    setPhone]   = useState(profile?.phone || '')
  const [waOptIn,  setWaOptIn] = useState(profile?.whatsapp_opt_in || 0)
  const [loading,  setLoading] = useState(false)
  const [error,    setError]   = useState('')

  async function submit(e) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const r = await submitEnquiry({
        course_slug: slug,
        course_type: course?.title || slug,
        phone:        phone || null,
        whatsapp_opt_in: waOptIn,
      })
      navigate('/thank-you', { state: {
        name:   user?.name,
        score:  r.data.lead_score,
        action: r.data.action,
      }})
    } catch(e) { setError(e.response?.data?.detail || 'Submission failed') }
    finally { setLoading(false) }
  }

  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8 pt-6">
          {course && <span className="text-4xl">{course.icon}</span>}
          <h1 className="font-display text-2xl font-extrabold text-navy mt-3 mb-1">Enquire About</h1>
          <p className="text-ember font-semibold">{course?.title || 'This Course'}</p>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8">
          {/* Pre-filled info */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-6 text-sm space-y-1">
            <p className="font-semibold text-navy mb-2">Your Details (from account)</p>
            <p><span className="text-slate-400">Name:</span> {user?.name}</p>
            <p><span className="text-slate-400">Email:</span> {user?.email}</p>
            {profile?.current_occupation && <p><span className="text-slate-400">Occupation:</span> {profile.current_occupation}</p>}
            {profile?.specialization && <p><span className="text-slate-400">Specialization:</span> {profile.specialization}</p>}
          </div>

          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="lbl">Phone Number (Optional)</label>
              <input value={phone} onChange={e=>setPhone(e.target.value)} type="tel"
                placeholder="+91 98765 43210" className="inp"/>
              <p className="text-slate-400 text-xs mt-1">Our advisor will call you at this number.</p>
            </div>

            <label className="flex items-start gap-3 cursor-pointer group">
              <input type="checkbox" checked={waOptIn===1} onChange={e=>setWaOptIn(e.target.checked?1:0)}
                className="mt-0.5 w-4 h-4 accent-ember"/>
              <span className="text-sm text-slate-600 group-hover:text-navy transition-colors">
                Send me course updates, schedules, and special offers via WhatsApp
              </span>
            </label>

            <p className="text-slate-400 text-xs bg-slate-50 border border-slate-100 rounded-lg px-3 py-2">
              📧 You'll receive a personalised email with course details and next steps after submission.
            </p>

            {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}

            <button type="submit" disabled={loading} className="w-full btn-primary">
              {loading ? '⏳ Submitting…' : '🚀 Submit Enquiry'}
            </button>
          </form>
        </div>
        <p className="text-center text-xs text-slate-400 mt-4">
          🔒 Your enquiry is secure. We'll never share your details with third parties.
        </p>
      </div>
    </main>
  )
}
