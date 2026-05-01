import { useState }         from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { submitEnquiry }    from '../utils/api'
import { useAuth }          from '../context/AuthContext'
import { getCourseBySlug, COURSES } from '../data/courses'

export default function Enquiry() {
  const { slug }          = useParams()
  const navigate          = useNavigate()
  const { user, profile } = useAuth()
  const course            = getCourseBySlug(slug)

  const [phone,   setPhone]   = useState(profile?.phone || '')
  const [waOptIn, setWaOptIn] = useState(profile?.whatsapp_opt_in || 0)
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')

  async function submit(e) {
    e.preventDefault()
    setError(''); setLoading(true)
    try {
      await submitEnquiry({
        course_slug: slug,
        course_type: course?.title || slug,
        phone:        phone || null,
        whatsapp_opt_in: waOptIn,
      })
      navigate('/thank-you', { state: { name: user?.name } })
    } catch (err) {
      setError(err.response?.data?.detail || 'Submission failed. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16 flex items-center justify-center px-4">
      <div className="w-full max-w-md">

        {/* Course header */}
        <div className="text-center mb-8 pt-6">
          {course && (
            <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${course.color}
                            flex items-center justify-center text-white
                            font-display font-bold text-lg mx-auto mb-4`}>
              {course.abbr}
            </div>
          )}
          <h1 className="font-display text-2xl font-extrabold text-navy">Enquire About</h1>
          <p className="text-ember font-semibold mt-1">{course?.title || slug}</p>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8">

          {/* Pre-filled account info */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 mb-6">
            <p className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">
              Your Details
            </p>
            <div className="space-y-1 text-sm">
              <div className="flex gap-2">
                <span className="text-slate-400 w-24">Name</span>
                <span className="text-slate-700 font-medium">{user?.name}</span>
              </div>
              <div className="flex gap-2">
                <span className="text-slate-400 w-24">Email</span>
                <span className="text-slate-700 font-medium">{user?.email}</span>
              </div>
              {profile?.current_occupation && (
                <div className="flex gap-2">
                  <span className="text-slate-400 w-24">Occupation</span>
                  <span className="text-slate-700 font-medium">{profile.current_occupation}</span>
                </div>
              )}
              {profile?.specialization && (
                <div className="flex gap-2">
                  <span className="text-slate-400 w-24">Specialization</span>
                  <span className="text-slate-700 font-medium">{profile.specialization}</span>
                </div>
              )}
            </div>
          </div>

          <form onSubmit={submit} className="space-y-5">
            {/* Phone */}
            <div>
              <label className="lbl">Phone Number (Optional)</label>
              <input
                type="tel" value={phone} onChange={e => setPhone(e.target.value)}
                placeholder="+91 98765 43210" className="inp"
              />
              <p className="text-slate-400 text-xs mt-1">
                Our advisor will call you at this number to discuss the course.
              </p>
            </div>

            {/* WhatsApp consent */}
            <label className="flex items-start gap-3 cursor-pointer group">
              <input type="checkbox"
                checked={waOptIn === 1}
                onChange={e => setWaOptIn(e.target.checked ? 1 : 0)}
                className="mt-0.5 w-4 h-4 accent-ember flex-shrink-0"
              />
              <span className="text-sm text-slate-600 group-hover:text-navy transition-colors leading-relaxed">
                Send me course updates, schedules, and offers via WhatsApp
              </span>
            </label>

            {/* Email note */}
            <div className="bg-slate-50 border border-slate-100 rounded-xl px-4 py-3 text-xs text-slate-500">
              You will receive a personalised email with course details and next steps at{' '}
              <span className="font-medium text-slate-700">{user?.email}</span>
            </div>

            {error && (
              <p className="text-red-600 text-sm bg-red-50 border border-red-200 rounded-xl px-4 py-2">
                {error}
              </p>
            )}

            <button type="submit" disabled={loading}
              className="w-full bg-ember hover:bg-orange-600 text-white font-bold py-3.5
                         rounded-xl transition-all active:scale-95 disabled:opacity-60">
              {loading ? 'Submitting…' : 'Submit Enquiry'}
            </button>
          </form>
        </div>

        <p className="text-center text-xs text-slate-400 mt-4">
          Your data is secure. We never share your details with third parties.
        </p>
      </div>
    </main>
  )
}
