import { useState }  from 'react'
import { Link }       from 'react-router-dom'
import { COURSES }    from '../data/courses'

const LEVELS    = ['All', 'Beginner', 'Intermediate', 'Advanced']
const DURATIONS = ['All', '< 4 Months', '4–6 Months', '> 6 Months']

export default function Courses() {
  const [level,    setLevel]    = useState('All')
  const [duration, setDuration] = useState('All')
  const [query,    setQuery]    = useState('')

  const filtered = COURSES.filter(c => {
    const mL = level === 'All' || c.level.toLowerCase().includes(level.toLowerCase())
    const mD = duration === 'All'
      || (duration === '< 4 Months'  && parseInt(c.duration) < 4)
      || (duration === '4–6 Months'  && parseInt(c.duration) >= 4 && parseInt(c.duration) <= 6)
      || (duration === '> 6 Months'  && parseInt(c.duration) > 6)
    const mQ = c.title.toLowerCase().includes(query.toLowerCase())
            || c.tagline.toLowerCase().includes(query.toLowerCase())
    return mL && mD && mQ
  })

  const pill = (active, val, set, col = 'navy') => (
    `px-4 py-2 rounded-full text-sm font-medium transition-all
     ${active === val
       ? col === 'ember' ? 'bg-ember text-white' : 'bg-navy text-white'
       : 'bg-white border border-slate-200 text-slate-600 hover:border-slate-400'}`
  )

  return (
    <main className="min-h-screen bg-slate-50 pt-20">

      {/* Header */}
      <div className="bg-navy px-6 py-14 text-center">
        <h1 className="font-display text-4xl md:text-5xl font-extrabold text-white mb-3">
          All Courses
        </h1>
        <p className="text-slate-400 max-w-xl mx-auto">
          Industry-designed programmes taught by practitioners, not just professors.
        </p>
      </div>

      <div className="max-w-7xl mx-auto px-6 py-10">

        {/* Filters */}
        <div className="flex flex-wrap gap-3 mb-8 items-center">
          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search courses…"
            className="border border-slate-200 rounded-xl px-4 py-2.5 text-sm bg-white
                       focus:outline-none focus:border-sky-accent w-52" />
          <div className="flex gap-2 flex-wrap">
            {LEVELS.map(l => (
              <button key={l} onClick={() => setLevel(l)} className={pill(level, l, setLevel)}>
                {l}
              </button>
            ))}
          </div>
          <div className="flex gap-2 flex-wrap">
            {DURATIONS.map(d => (
              <button key={d} onClick={() => setDuration(d)} className={pill(duration, d, setDuration, 'ember')}>
                {d}
              </button>
            ))}
          </div>
          <p className="text-slate-400 text-sm ml-auto">{filtered.length} courses</p>
        </div>

        {/* Grid */}
        <div className="grid sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {filtered.map(c => (
            <Link to={`/courses/${c.slug}`} key={c.id}
              className="group card-hover bg-white border border-slate-200 rounded-2xl overflow-hidden">
              <div className={`h-1.5 bg-gradient-to-r ${c.color}`} />
              <div className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className={`w-10 h-10 rounded-xl bg-gradient-to-br ${c.color}
                                   flex items-center justify-center text-white
                                   font-display font-bold text-xs`}>
                    {c.abbr}
                  </div>
                  {c.badge && (
                    <span className={`text-xs font-semibold px-2.5 py-1 rounded-full ${c.badgeColor}`}>
                      {c.badge}
                    </span>
                  )}
                </div>
                <h3 className="font-display font-bold text-navy text-sm mb-1
                               group-hover:text-ember transition-colors">
                  {c.title}
                </h3>
                <p className="text-slate-500 text-xs mb-3 leading-relaxed">{c.tagline}</p>
                <div className="space-y-1 mb-3">
                  {c.outcomes.slice(0, 2).map(o => (
                    <p key={o} className="text-xs text-slate-500 flex items-start gap-1.5">
                      <svg className="w-3.5 h-3.5 text-green-500 mt-0.5 flex-shrink-0"
                        fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                      {o}
                    </p>
                  ))}
                </div>
                <div className="flex items-center justify-between text-xs text-slate-400
                                pt-3 border-t border-slate-100">
                  <span>{c.duration}</span>
                  <span>{c.rating} / 5 · {(c.enrolled / 1000).toFixed(1)}K</span>
                  <span className="text-ember font-bold">₹{(c.price / 1000).toFixed(0)}K</span>
                </div>
              </div>
            </Link>
          ))}
        </div>

        {!filtered.length && (
          <div className="text-center py-20 text-slate-400">
            <p className="text-lg">No courses match your filters.</p>
            <button onClick={() => { setLevel('All'); setDuration('All'); setQuery('') }}
              className="mt-4 text-sm text-sky-accent hover:underline">
              Clear all filters
            </button>
          </div>
        )}
      </div>
    </main>
  )
}