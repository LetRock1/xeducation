import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate }           from 'react-router-dom'
import { useAuth }                     from '../context/AuthContext'
import { tracker }                     from '../utils/tracker'
import { COURSES }                     from '../data/courses'
import RecommendedCourses              from '../components/RecommendedCourses'

const STATS = [
  { value: '500K+', label: 'Learners Enrolled' },
  { value: '94%',   label: 'Placement Rate' },
  { value: '₹8L+',  label: 'Avg Salary Jump' },
  { value: '40+',   label: 'Countries' },
]

const TESTIMONIALS = [
  { name: 'Aditi Sharma',  role: 'Data Analyst @ Infosys',          text: 'The capstone project alone got me my job. Practical from Day 1.', stars: 5, av: 'AS' },
  { name: 'Rohit Verma',   role: 'Marketing Lead @ Swiggy',          text: 'The Google Ads module directly got me a 40% salary increase.', stars: 5, av: 'RV' },
  { name: 'Sneha Pillai',  role: 'Finance Manager @ HDFC',           text: 'Real deal structures — not just theory. Worth every rupee.', stars: 5, av: 'SP' },
  { name: 'Kiran Patel',   role: 'SCM Analyst @ Mahindra',           text: 'Ex-Amazon instructor. Every session was industry-grade content.', stars: 5, av: 'KP' },
]

function useReveal() {
  const ref = useRef(null)
  const [vis, setVis] = useState(false)
  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => { if (e.isIntersecting) setVis(true) }, { threshold: 0.12 })
    if (ref.current) obs.observe(ref.current)
    return () => obs.disconnect()
  }, [])
  return [ref, vis]
}

function CourseCard({ c, visible, delay }) {
  return (
    <Link to={`/courses/${c.slug}`}
      className={`group card-hover bg-white border border-slate-200 rounded-2xl overflow-hidden
        transition-all duration-700 ${visible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}
      style={{ transitionDelay: `${delay}ms` }}>
      <div className={`h-1.5 bg-gradient-to-r ${c.color}`} />
      <div className="p-5">
        <div className="flex items-start justify-between mb-3">
          <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${c.color} flex items-center
                           justify-center text-white font-display font-bold text-xs`}>
            {c.abbr}
          </div>
          {c.badge && (
            <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${c.badgeColor}`}>
              {c.badge}
            </span>
          )}
        </div>
        <h3 className="font-display font-bold text-navy text-sm mb-1 group-hover:text-ember transition-colors">
          {c.title}
        </h3>
        <p className="text-slate-500 text-xs mb-3 leading-relaxed">{c.tagline}</p>
        <div className="flex items-center justify-between text-xs text-slate-400 pt-3 border-t border-slate-100">
          <span>{c.duration}</span>
          <span>{c.rating} / 5</span>
          <span className="text-ember font-bold">₹{(c.price / 1000).toFixed(0)}K</span>
        </div>
      </div>
    </Link>
  )
}

export default function Home() {
  const navigate        = useNavigate()
  const { user, profile } = useAuth()
  const [statsRef,  statsVis]  = useReveal()
  const [courseRef, courseVis] = useReveal()
  const [testiRef,  testiVis]  = useReveal()
  const webinarRef = useRef(null)

  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { tracker.testimonial(null); obs.disconnect() }
    }, { threshold: 0.3 })
    if (testiRef.current) obs.observe(testiRef.current)
  }, [testiRef])

  useEffect(() => {
    const obs = new IntersectionObserver(([e]) => {
      if (e.isIntersecting) { tracker.webinar(null); obs.disconnect() }
    }, { threshold: 0.4 })
    if (webinarRef.current) obs.observe(webinarRef.current)
  }, [])

  return (
    <main className="bg-white">

      {/* HERO */}
      <section className="relative min-h-screen bg-navy overflow-hidden flex items-center pt-20">
        <div className="absolute inset-0 opacity-[0.035]"
          style={{ backgroundImage: 'linear-gradient(#38BDF8 1px,transparent 1px),linear-gradient(90deg,#38BDF8 1px,transparent 1px)', backgroundSize: '60px 60px' }} />
        <div className="max-w-7xl mx-auto px-6 py-24 grid md:grid-cols-2 gap-16 items-center">
          <div>
            <div className="inline-flex items-center gap-2 bg-white/10 border border-white/20
                            rounded-full px-4 py-1.5 text-sm text-sky-accent font-medium mb-6">
              <span className="w-2 h-2 bg-green-400 rounded-full" />
              Now Enrolling — March 2026 Cohort
            </div>

            {user ? (
              <h1 className="font-display text-5xl md:text-6xl font-extrabold text-white leading-[1.1] mb-4">
                Welcome back,<br />
                <span className="text-gradient">{user.name.split(' ')[0]}</span>
              </h1>
            ) : (
              <h1 className="font-display text-5xl md:text-6xl font-extrabold text-white leading-[1.1] mb-4">
                Your Career's<br />
                <span className="text-gradient">Next Chapter</span><br />
                Starts Here.
              </h1>
            )}

            <p className="text-slate-400 text-lg leading-relaxed mb-8 max-w-xl">
              {user
                ? `Continue your journey${profile?.current_occupation ? ` as a ${profile.current_occupation}` : ''}. Your personalised course recommendations are below.`
                : 'Industry-validated online programmes built for professionals who need real skills, not textbook theory.'}
            </p>

            <div className="flex flex-wrap gap-4">
              <button onClick={() => navigate('/courses')}
                className="bg-ember hover:bg-orange-600 text-white font-semibold px-7 py-3.5
                           rounded-xl transition-all active:scale-95 shadow-lg shadow-ember/30">
                {user ? 'Browse Courses' : 'Explore Courses'}
              </button>
              {!user && (
                <button onClick={() => navigate('/signup')}
                  className="border-2 border-white/30 text-white font-semibold px-7 py-3.5
                             rounded-xl hover:border-sky-accent hover:text-sky-accent transition-all">
                  Create Free Account
                </button>
              )}
            </div>
          </div>

          {/* Hero card */}
          <div className="hidden md:flex justify-center">
            <div className="relative w-80">
              <div className="absolute -inset-2 bg-gradient-to-br from-sky-accent/30 to-gold/30 rounded-3xl blur-xl" />
              <div className="relative bg-navy-light border border-white/20 rounded-2xl p-6 space-y-4">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-blue-600 to-cyan-500
                                  flex items-center justify-center text-white font-display font-bold">
                    DS
                  </div>
                  <div>
                    <p className="text-white font-display font-semibold text-sm">Data Science & Analytics</p>
                    <p className="text-slate-400 text-xs">6 Months · 12,400 enrolled</p>
                  </div>
                </div>
                <div className="bg-white/5 rounded-xl p-3">
                  <div className="flex justify-between text-xs text-slate-400 mb-1.5">
                    <span>Your progress</span><span>Week 4 of 24</span>
                  </div>
                  <div className="w-full bg-white/10 rounded-full h-1.5">
                    <div className="bg-gradient-to-r from-sky-accent to-gold h-1.5 rounded-full w-[17%]" />
                  </div>
                </div>
                {['Machine Learning', 'SQL Mastery', 'Tableau Dashboards'].map(t => (
                  <div key={t} className="flex items-center gap-2 text-sm text-slate-300">
                    <svg className="w-4 h-4 text-green-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                    </svg>
                    {t}
                  </div>
                ))}
                <div className="pt-2 border-t border-white/10">
                  <p className="text-gold font-semibold text-xs">98% placement rate · ₹12L avg CTC</p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* STATS */}
      <section ref={statsRef} className="bg-navy border-b border-white/10">
        <div className="max-w-7xl mx-auto px-6 py-12 grid grid-cols-2 md:grid-cols-4 gap-8">
          {STATS.map((s, i) => (
            <div key={s.label}
              className={`text-center transition-all duration-700 delay-[${i * 100}ms]
                ${statsVis ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-6'}`}>
              <p className="font-display text-4xl font-extrabold text-white mb-1">{s.value}</p>
              <p className="text-slate-500 text-sm">{s.label}</p>
            </div>
          ))}
        </div>
      </section>

      {/* RECOMMENDATIONS (logged-in only) */}
      {user && <div className="bg-white"><RecommendedCourses /></div>}

      {/* COURSES GRID */}
      <section ref={courseRef} className="py-20 px-6 max-w-7xl mx-auto">
        <div className={`text-center mb-12 transition-all duration-700
          ${courseVis ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
          <p className="text-ember font-semibold text-sm tracking-widest uppercase mb-3">Our Programmes</p>
          <h2 className="font-display text-4xl font-extrabold text-navy mb-3">
            Courses Built for the <span className="text-gradient">Real World</span>
          </h2>
          <p className="text-slate-500 max-w-xl mx-auto text-sm">
            Not theory. Not textbooks. Live projects, real mentors, an alumni network that opens doors.
          </p>
        </div>
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {COURSES.map((c, i) => (
            <CourseCard key={c.id} c={c} visible={courseVis} delay={i * 60} />
          ))}
        </div>
        <div className="text-center mt-10">
          <Link to="/courses"
            className="inline-block border-2 border-sky-accent text-sky-accent font-semibold
                       px-6 py-3 rounded-xl hover:bg-sky-accent hover:text-navy transition-all">
            View All Courses
          </Link>
        </div>
      </section>

      {/* TESTIMONIALS */}
      <section ref={testiRef} className="py-20 bg-slate-50">
        <div className="max-w-7xl mx-auto px-6">
          <div className={`text-center mb-12 transition-all duration-700
            ${testiVis ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8'}`}>
            <p className="text-ember font-semibold text-sm tracking-widest uppercase mb-3">Success Stories</p>
            <h2 className="font-display text-4xl font-extrabold text-navy">
              Real People. <span className="text-gradient">Real Results.</span>
            </h2>
          </div>
          <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
            {TESTIMONIALS.map((t, i) => (
              <div key={t.name}
                className={`bg-white border border-slate-200 rounded-2xl p-6 card-hover
                  transition-all duration-700 delay-[${i * 100}ms]
                  ${testiVis ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-10'}`}>
                <div className="flex gap-0.5 text-gold mb-4">
                  {'★'.repeat(t.stars)}
                </div>
                <p className="text-slate-600 text-sm leading-relaxed mb-5 italic">"{t.text}"</p>
                <div className="flex items-center gap-3 pt-4 border-t border-slate-100">
                  <div className="w-10 h-10 rounded-full bg-navy flex items-center
                                  justify-center text-sky-accent text-sm font-bold font-display">
                    {t.av}
                  </div>
                  <div>
                    <p className="font-semibold text-navy text-sm">{t.name}</p>
                    <p className="text-slate-400 text-xs">{t.role}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* WEBINAR */}
      <section ref={webinarRef} className="bg-navy py-20 px-6">
        <div className="max-w-3xl mx-auto text-center">
          <p className="inline-block bg-gold/20 text-gold text-sm font-semibold
                        px-4 py-1.5 rounded-full mb-6">
            Free Live Webinar
          </p>
          <h2 className="font-display text-4xl font-extrabold text-white mb-4">
            Is an Online Course Worth It In 2026?
          </h2>
          <p className="text-slate-400 text-lg mb-8">
            Join 2,000+ professionals every Saturday at 11 AM IST. Alumni share real salary data,
            career pivots, and honest reviews. No sales pitch.
          </p>
          <button
            onClick={() => navigate(user ? '/courses' : '/signup')}
            className="bg-gold hover:bg-yellow-400 text-navy font-bold px-8 py-4 rounded-xl
                       transition-all active:scale-95 shadow-lg shadow-gold/30">
            {user ? 'Browse Courses' : 'Reserve Your Free Seat'}
          </button>
          <p className="text-slate-600 text-sm mt-4">
            Next session: Saturday, 11 AM IST · 47 seats remaining
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="bg-ember py-14 px-6">
        <div className="max-w-4xl mx-auto flex flex-col md:flex-row items-center justify-between gap-6">
          <div>
            <h3 className="font-display text-2xl font-bold text-white mb-1">
              Not sure which course is right for you?
            </h3>
            <p className="text-white/80">
              Talk to an advisor in under 5 minutes — free, no obligation.
            </p>
          </div>
          <button
            onClick={() => navigate(user ? '/courses' : '/signup')}
            className="bg-white text-ember font-bold px-7 py-3.5 rounded-xl whitespace-nowrap
                       hover:bg-slate-100 transition-all active:scale-95">
            {user ? 'Browse Courses' : 'Book Free Counselling'}
          </button>
        </div>
      </section>

    </main>
  )
}