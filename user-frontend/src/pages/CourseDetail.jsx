import { useEffect, useRef, useState } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useAuth }          from '../context/AuthContext'
import { getCourseBySlug }  from '../data/courses'
import { addToCart, addToWishlist } from '../utils/api'
import { tracker }          from '../utils/tracker'
import ReviewSection        from '../components/ReviewSection'
import QnASection           from '../components/QnASection'

function LockGate({ message }) {
  const navigate = useNavigate()
  return (
    <div className="bg-slate-50 border-2 border-dashed border-slate-200 rounded-2xl p-10 text-center my-6">
      <div className="w-10 h-10 bg-slate-200 rounded-full flex items-center justify-center mx-auto mb-4">
        <svg className="w-5 h-5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"/>
        </svg>
      </div>
      <p className="font-display font-bold text-navy text-base mb-2">{message}</p>
      <p className="text-slate-500 text-sm mb-5">Create a free account to access this content.</p>
      <div className="flex gap-3 justify-center">
        <button onClick={() => navigate('/signup')}
          className="bg-ember hover:bg-orange-600 text-white font-semibold text-sm
                     px-5 py-2.5 rounded-xl transition-all">
          Sign Up Free
        </button>
        <button onClick={() => navigate('/login')}
          className="border-2 border-slate-300 text-slate-600 font-semibold text-sm
                     px-5 py-2.5 rounded-xl hover:border-navy hover:text-navy transition-all">
          Login
        </button>
      </div>
    </div>
  )
}

function CheckIcon() {
  return (
    <svg className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
    </svg>
  )
}

export default function CourseDetail() {
  const { slug }   = useParams()
  const navigate   = useNavigate()
  const { user }   = useAuth()
  const course     = getCourseBySlug(slug)
  const pricingRef = useRef(null)
  const testiRef   = useRef(null)
  const [videoPlayed,  setVideoPlayed]  = useState(false)
  const [cartMsg,      setCartMsg]      = useState('')
  const [wishlistMsg,  setWishlistMsg]  = useState('')
  const [timeStart]    = useState(Date.now())

  useEffect(() => {
    if (!course) return
    const pObs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { tracker.pricing(slug); pObs.disconnect() }
    }, { threshold: 0.4 })
    const tObs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { tracker.testimonial(slug); tObs.disconnect() }
    }, { threshold: 0.3 })
    if (pricingRef.current) pObs.observe(pricingRef.current)
    if (testiRef.current)   tObs.observe(testiRef.current)
    return () => { pObs.disconnect(); tObs.disconnect() }
  }, [course])

  useEffect(() => {
    tracker.pageView(slug, 0)
    return () => {
      const sec = Math.floor((Date.now() - timeStart) / 1000)
      tracker.pageView(slug, sec)
    }
  }, [])

  function handleVideo() {
    if (!user) { navigate('/login'); return }
    if (!videoPlayed) { tracker.video(slug); setVideoPlayed(true) }
  }

  function handleBrochure() {
    if (!user) { navigate('/login'); return }
    tracker.brochure(slug)
    alert(`Brochure for "${course.title}" — connect a real PDF in production.`)
  }

  async function handleCart() {
    if (!user) { navigate('/login'); return }
    try {
      await addToCart({ course_slug: slug, course_title: course.title, price: course.price })
      tracker.cartAdd(slug)
      setCartMsg('Added to cart')
      setTimeout(() => setCartMsg(''), 3000)
    } catch (e) {
      setCartMsg(e.response?.data?.detail || 'Could not add to cart')
    }
  }

  async function handleWishlist() {
    if (!user) { navigate('/login'); return }
    try {
      await addToWishlist({ course_slug: slug, course_title: course.title })
      tracker.wishlistAdd(slug)
      setWishlistMsg('Saved to wishlist')
      setTimeout(() => setWishlistMsg(''), 3000)
    } catch (e) {
      setWishlistMsg(e.response?.data?.detail || 'Could not save')
    }
  }

  if (!course) return (
    <div className="min-h-screen flex items-center justify-center pt-20">
      <div className="text-center">
        <p className="text-xl text-slate-600 mb-4">Course not found.</p>
        <Link to="/courses"
          className="bg-ember text-white font-semibold px-6 py-3 rounded-xl hover:bg-orange-600">
          Browse All Courses
        </Link>
      </div>
    </div>
  )

  return (
    <main className="min-h-screen bg-white pt-20">

      {/* Hero */}
      <section className="relative bg-navy overflow-hidden py-16 px-6">
        <div className={`absolute inset-0 bg-gradient-to-br ${course.color} opacity-10`} />
        <div className="max-w-7xl mx-auto relative">
          <p className="text-slate-500 text-sm mb-4">
            <Link to="/courses" className="hover:text-white transition-colors">Courses</Link>
            {' / '}
            <span className="text-white">{course.title}</span>
          </p>

          <div className="grid md:grid-cols-2 gap-12 items-center">
            <div>
              <div className="flex items-center gap-3 mb-4">
                <div className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${course.color}
                                 flex items-center justify-center text-white
                                 font-display font-bold text-lg`}>
                  {course.abbr}
                </div>
                {course.badge && (
                  <span className={`text-xs font-bold px-3 py-1.5 rounded-full ${course.badgeColor}`}>
                    {course.badge}
                  </span>
                )}
              </div>
              <h1 className="font-display text-4xl font-extrabold text-white mb-3">{course.title}</h1>
              <p className="text-slate-300 text-lg mb-4">{course.tagline}</p>
              <div className="flex flex-wrap gap-4 text-sm text-slate-400 mb-6">
                <span>{course.duration}</span>
                <span>·</span>
                <span>{course.level}</span>
                <span>·</span>
                <span>{course.rating} / 5 · {course.enrolled.toLocaleString()} enrolled</span>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  onClick={() => user ? navigate(`/enquiry/${slug}`) : navigate('/signup')}
                  className="bg-ember hover:bg-orange-600 text-white font-bold px-7 py-3.5
                             rounded-xl transition-all active:scale-95 shadow-lg shadow-ember/30">
                  Enquire Now — ₹{course.price.toLocaleString()}
                </button>
                <button onClick={handleCart}
                  className="border-2 border-white/30 text-white font-semibold px-5 py-3.5
                             rounded-xl hover:border-sky-accent hover:text-sky-accent transition-all">
                  Add to Cart
                </button>
                <button onClick={handleWishlist}
                  className="border-2 border-white/30 text-white font-semibold px-5 py-3.5
                             rounded-xl hover:border-red-400 hover:text-red-400 transition-all">
                  Save
                </button>
              </div>
              {cartMsg    && <p className="text-sky-accent text-sm mt-3">{cartMsg}</p>}
              {wishlistMsg && <p className="text-sky-accent text-sm mt-3">{wishlistMsg}</p>}
            </div>

            {/* Video preview */}
            <div onClick={handleVideo}
              className="relative bg-white/5 border border-white/20 rounded-2xl overflow-hidden
                         aspect-video cursor-pointer group">
              <div className={`absolute inset-0 bg-gradient-to-br ${course.color} opacity-20`} />
              <div className="absolute inset-0 flex items-center justify-center">
                <div className="w-14 h-14 bg-white/20 backdrop-blur rounded-full flex items-center
                                justify-center group-hover:bg-white/30 transition-all">
                  <svg className="w-6 h-6 text-white ml-1" fill="currentColor" viewBox="0 0 24 24">
                    <path d="M8 5v14l11-7z" />
                  </svg>
                </div>
              </div>
              <p className="absolute bottom-4 left-4 text-white text-sm font-semibold">
                Course overview · 3 min
              </p>
              {!user && (
                <div className="absolute top-3 right-3 bg-black/60 text-white text-xs px-2 py-1 rounded-full">
                  Login to watch
                </div>
              )}
              {videoPlayed && (
                <div className="absolute top-3 right-3 bg-green-600 text-white text-xs px-2 py-1 rounded-full">
                  Watched
                </div>
              )}
            </div>
          </div>
        </div>
      </section>

      {/* Outcomes + Instructor */}
      <section className="max-w-7xl mx-auto px-6 py-14 grid md:grid-cols-2 gap-12">
        <div>
          <h2 className="font-display text-2xl font-bold text-navy mb-5">What You'll Learn</h2>
          <div className="space-y-3">
            {course.outcomes.map(o => (
              <div key={o} className="flex items-start gap-3 bg-slate-50 border border-slate-100 rounded-xl px-4 py-3">
                <CheckIcon />
                <p className="text-slate-700 text-sm">{o}</p>
              </div>
            ))}
          </div>
        </div>
        <div>
          <h2 className="font-display text-2xl font-bold text-navy mb-5">Your Instructor</h2>
          <div className="bg-slate-50 border border-slate-100 rounded-2xl p-6">
            <div className="flex items-center gap-4 mb-4">
              <div className="w-14 h-14 rounded-full bg-navy flex items-center
                              justify-center text-sky-accent font-display font-bold text-lg">
                {course.instructor.name.split(' ').map(w => w[0]).join('').slice(0, 2)}
              </div>
              <div>
                <p className="font-display font-bold text-navy">{course.instructor.name}</p>
                <p className="text-slate-500 text-sm">{course.instructor.role}</p>
                <p className="text-slate-400 text-xs">{course.instructor.exp} experience</p>
              </div>
            </div>
            <p className="text-slate-600 text-sm leading-relaxed">
              An industry veteran who brings real-world experience into every session.
              No textbook fluff — only practical, battle-tested knowledge.
            </p>
          </div>
        </div>
      </section>

      {/* Curriculum — GATED */}
      <section className="bg-slate-50 py-14 px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="font-display text-2xl font-bold text-navy mb-6 text-center">
            Programme Curriculum
          </h2>
          {user ? (
            <div className="max-w-2xl mx-auto space-y-3">
              {course.curriculum.map((m, i) => (
                <div key={m.w}
                  className="bg-white border border-slate-200 rounded-xl px-5 py-4
                             flex items-center gap-4">
                  <div className={`w-9 h-9 rounded-full bg-gradient-to-br ${course.color}
                                   flex items-center justify-center text-white
                                   font-bold text-sm flex-shrink-0`}>
                    {i + 1}
                  </div>
                  <div>
                    <p className="text-xs text-slate-400 font-semibold uppercase tracking-wide">{m.w}</p>
                    <p className="text-slate-700 font-medium text-sm">{m.t}</p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="max-w-lg mx-auto">
              <LockGate message="Login to view the full curriculum" />
            </div>
          )}
        </div>
      </section>

      {/* Brochure — GATED */}
      <section className="max-w-7xl mx-auto px-6 py-10 text-center">
        {user ? (
          <button onClick={handleBrochure}
            className="inline-flex items-center gap-2 border-2 border-sky-accent text-sky-accent
                       font-semibold px-6 py-3 rounded-xl hover:bg-sky-accent hover:text-navy transition-all">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"/>
            </svg>
            Download Course Brochure (PDF)
          </button>
        ) : (
          <div className="max-w-md mx-auto">
            <LockGate message="Login to download the course brochure" />
          </div>
        )}
      </section>

      {/* Reviews — GATED */}
      <section ref={testiRef} className="bg-slate-50 py-10 px-6">
        <div className="max-w-7xl mx-auto">
          <h2 className="font-display text-2xl font-bold text-navy text-center mb-6">
            Student Reviews
          </h2>
          {user ? (
            <ReviewSection courseSlug={slug} />
          ) : (
            <div className="max-w-md mx-auto">
              <LockGate message="Login to read and write reviews" />
            </div>
          )}
        </div>
      </section>

      {/* Q&A — GATED */}
      {user ? (
        <QnASection courseSlug={slug} />
      ) : (
        <div className="max-w-md mx-auto px-6 py-10">
          <LockGate message="Login to ask questions and get expert answers" />
        </div>
      )}

      {/* Pricing — TRACKED */}
      <section ref={pricingRef} className="bg-navy py-16 px-6">
        <div className="max-w-2xl mx-auto text-center">
          <p className="text-slate-400 text-sm uppercase tracking-widest mb-2">Pricing</p>
          <h2 className="font-display text-4xl font-extrabold text-white mb-2">
            ₹{course.price.toLocaleString()}
          </h2>
          <p className="text-slate-400 mb-2">
            or ₹{course.emi.toLocaleString()} / month — 0% interest EMI
          </p>
          <p className="text-green-400 text-sm mb-8">
            7-day money-back guarantee · Lifetime access · Alumni network
          </p>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <button onClick={handleCart}
              className="bg-white text-navy font-bold px-8 py-4 rounded-xl
                         hover:bg-slate-100 transition-all active:scale-95">
              Add to Cart
            </button>
            <button
              onClick={() => user ? navigate(`/enquiry/${slug}`) : navigate('/signup')}
              className="bg-ember hover:bg-orange-600 text-white font-bold px-8 py-4
                         rounded-xl transition-all active:scale-95 shadow-lg shadow-ember/30">
              Enquire Now
            </button>
          </div>
          <p className="text-slate-600 text-xs mt-4">
            Secure checkout · GST invoice provided
          </p>
        </div>
      </section>

    </main>
  )
}