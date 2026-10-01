import { useEffect, useState } from 'react'
import { Link }                from 'react-router-dom'
import { getDashboard, getLiveScore, removeFromWishlist } from '../utils/api'
import { useAuth } from '../context/AuthContext'

function ScoreRing({ score }) {
  const color = score >= 80 ? '#f97316' : score >= 60 ? '#f59e0b' : score >= 40 ? '#64748b' : '#94a3b8'
  return (
    <div className="relative w-20 h-20">
      <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
        <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e2e8f0" strokeWidth="3" />
        <circle cx="18" cy="18" r="15.9" fill="none"
          stroke={color} strokeWidth="3"
          strokeDasharray={`${score} ${100 - score}`} strokeLinecap="round" />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-lg font-extrabold text-navy leading-none">{score}</span>
        <span className="text-slate-400 text-xs leading-none mt-0.5">/100</span>
      </div>
    </div>
  )
}

export default function UserDashboard() {
  const { user, profile } = useAuth()
  const [data,       setData]       = useState(null)
  const [liveScore,  setLiveScore]  = useState(null)
  const [persona,    setPersona]    = useState(null)
  const [loading,    setLoading]    = useState(true)

  // Fetch main dashboard data (cart, wishlist, purchases, coupons)
  const load = () =>
    getDashboard()
      .then(r => setData(r.data))
      .catch(() => {})
      .finally(() => setLoading(false))

  // Fetch live score separately
  useEffect(() => {
    load()
    getLiveScore()
      .then(r => {
        setLiveScore(r.data.lead_score)
        setPersona(r.data.persona)
      })
      .catch(() => {})
  }, [])

  async function removeWishlist(slug) {
    await removeFromWishlist(slug).catch(() => {})
    load()
  }

  if (loading) return (
    <div className="min-h-screen pt-24 flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin" />
    </div>
  )

  // Use live score if available, otherwise fallback to null
  const score = liveScore !== null ? Math.round(liveScore) : null

  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16">
      <div className="max-w-5xl mx-auto px-6 py-8">

        {/* Header */}
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display text-3xl font-extrabold text-navy">
              {user?.name?.split(' ')[0]}'s Dashboard
            </h1>
            <p className="text-slate-500 text-sm mt-1">
              {profile?.current_occupation || 'Complete your profile to get started'}
            </p>
          </div>
          {score !== null && (
            <div className="flex items-center gap-4 bg-white border border-slate-200 rounded-2xl px-5 py-3">
              <ScoreRing score={score} />
              <div>
                <p className="font-display font-bold text-navy text-sm">Live Lead Score</p>
                <p className="text-slate-500 text-xs">{persona || 'Calculating…'}</p>
              </div>
            </div>
          )}
        </div>

        {/* Reward banner */}
        {data?.coupons?.length > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-2xl px-6 py-4 mb-6 flex items-center justify-between">
            <div>
              <p className="font-display font-bold text-amber-900 text-sm">You have an exclusive offer</p>
              <p className="text-amber-800 text-sm mt-0.5">
                Use code{' '}
                <span className="font-mono font-bold text-ember">{data.coupons[0].coupon_code}</span>
                {' '}for {data.coupons[0].discount_pct}% off at checkout.
              </p>
            </div>
            <Link to="/cart"
              className="bg-amber-600 hover:bg-amber-700 text-white font-semibold text-sm px-5 py-2.5 rounded-xl transition-all whitespace-nowrap">
              Apply Now
            </Link>
          </div>
        )}

        {/* Profile incomplete banner */}
        {!profile?.profile_complete && (
          <div className="bg-blue-50 border border-blue-200 rounded-2xl px-6 py-4 mb-6 flex items-center justify-between">
            <div>
              <p className="font-semibold text-blue-900 text-sm">Complete your profile for personalised recommendations</p>
              <p className="text-blue-700 text-xs mt-0.5">Takes 60 seconds — we use this to match you with the right courses.</p>
            </div>
            <Link to="/complete-profile"
              className="bg-blue-600 hover:bg-blue-700 text-white text-sm px-4 py-2 rounded-xl transition-all whitespace-nowrap">
              Complete
            </Link>
          </div>
        )}

        <div className="grid md:grid-cols-3 gap-6">

          {/* Main content */}
          <div className="md:col-span-2 space-y-8">

            {/* Purchased courses */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-display font-bold text-navy text-lg">My Courses</h2>
                <Link to="/courses" className="text-sky-accent text-sm hover:underline">Browse more</Link>
              </div>
              {!data?.purchases?.length ? (
                <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center">
                  <p className="text-slate-400 text-sm mb-3">You haven't enrolled in any courses yet.</p>
                  <Link to="/courses"
                    className="inline-block text-sm bg-ember hover:bg-orange-600 text-white font-semibold px-5 py-2.5 rounded-xl transition-all">
                    Browse Courses
                  </Link>
                </div>
              ) : (
                <div className="space-y-3">
                  {data.purchases.map(p => (
                    <div key={p.id}
                      className="bg-white border border-slate-200 rounded-2xl px-5 py-4 flex items-center justify-between">
                      <div>
                        <p className="font-semibold text-navy">{p.course_title}</p>
                        <p className="text-slate-400 text-xs mt-0.5">
                          Enrolled {new Date(p.purchased_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })}
                        </p>
                        {p.coupon_used && (
                          <p className="text-green-600 text-xs mt-0.5">
                            Coupon applied: {p.coupon_used} — saved ₹{p.discount_amount?.toLocaleString()}
                          </p>
                        )}
                      </div>
                      <span className="bg-green-100 text-green-700 text-xs font-semibold px-3 py-1.5 rounded-full">
                        Enrolled
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Wishlist */}
            <div>
              <div className="flex items-center justify-between mb-4">
                <h2 className="font-display font-bold text-navy text-lg">Saved Courses</h2>
                <Link to="/wishlist" className="text-sky-accent text-sm hover:underline">View all</Link>
              </div>
              {!data?.wishlist?.length ? (
                <p className="text-slate-400 text-sm bg-white border border-slate-200 rounded-2xl px-5 py-4">
                  No courses saved yet. Click "Save" on any course page to add it here.
                </p>
              ) : (
                <div className="space-y-3">
                  {data.wishlist.map(w => (
                    <div key={w.id}
                      className="bg-white border border-slate-200 rounded-2xl px-5 py-4 flex items-center justify-between gap-4">
                      <p className="font-semibold text-navy text-sm flex-1 min-w-0 truncate">
                        {w.course_title}
                      </p>
                      <div className="flex items-center gap-2 flex-shrink-0">
                        <Link to={`/courses/${w.course_slug}`}
                          className="text-sm text-slate-600 border border-slate-200 px-3 py-1.5
                                     rounded-lg hover:border-navy hover:text-navy transition-all">
                          View
                        </Link>
                        <button
                          onClick={() => removeWishlist(w.course_slug)}
                          className="p-1.5 text-slate-300 hover:text-red-500 hover:bg-red-50
                                     rounded-lg transition-all"
                          title="Remove from saved">
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                          </svg>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

          </div>

          {/* Sidebar */}
          <div className="space-y-4">
            <h2 className="font-display font-bold text-navy text-lg">Quick Actions</h2>

            {[
              { label: 'View Cart', to: '/cart', sub: `${data?.cart?.length || 0} item${data?.cart?.length !== 1 ? 's' : ''}` },
              { label: 'Saved Courses', to: '/wishlist', sub: `${data?.wishlist?.length || 0} saved` },
              { label: 'Browse Courses', to: '/courses', sub: 'Explore all 8 programmes' },
              { label: 'Edit Profile', to: '/complete-profile', sub: 'Update your details' },
            ].map(a => (
              <Link key={a.to} to={a.to}
                className="block bg-white border border-slate-200 rounded-xl px-4 py-3.5
                           hover:border-navy transition-all group">
                <p className="font-medium text-slate-700 group-hover:text-navy text-sm transition-colors">
                  {a.label}
                </p>
                <p className="text-slate-400 text-xs mt-0.5">{a.sub}</p>
              </Link>
            ))}

            {/* Active coupons */}
            {data?.coupons?.length > 0 && (
              <div className="bg-white border border-slate-200 rounded-xl px-4 py-4">
                <p className="font-semibold text-navy text-sm mb-3">Active Coupons</p>
                {data.coupons.map(c => (
                  <div key={c.id} className="flex items-center justify-between py-1.5 border-b border-slate-100 last:border-0">
                    <span className="font-mono text-ember font-bold text-sm">{c.coupon_code}</span>
                    <span className="text-green-600 text-xs font-semibold">{c.discount_pct}% off</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </main>
  )
}