import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRecommendations } from '../utils/api'
import { COURSES } from '../data/courses'

// Full slug map for all 24 courses
const TITLE_TO_SLUG = {}
COURSES.forEach(c => { TITLE_TO_SLUG[c.title] = c.slug })

export default function RecommendedCourses() {
  const [recs, setRecs] = useState([])

  useEffect(() => {
    getRecommendations()
      .then(r => {
        const titles  = r.data.recommendations || []
        const courses = titles
          .map(t => COURSES.find(c => c.title === t))
          .filter(Boolean)
          .slice(0, 4)
        setRecs(courses)
      })
      .catch(() => {})
  }, [])

  if (!recs.length) return null

  return (
    <section className="py-10 px-6 max-w-7xl mx-auto">
      <h2 className="font-display text-xl font-bold text-navy mb-1">
        Recommended for You
      </h2>
      <p className="text-slate-500 text-sm mb-6">
        Based on your profile and browsing activity
      </p>

      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {recs.map(c => (
          <Link key={c.id} to={`/courses/${c.slug}`}
            className="group card-hover bg-white border border-slate-200 rounded-2xl overflow-hidden">
            <div className={`h-1.5 bg-gradient-to-r ${c.color}`} />
            <div className="p-4">
              <div className={`w-9 h-9 rounded-lg bg-gradient-to-br ${c.color}
                              flex items-center justify-center text-white
                              font-display font-bold text-xs mb-3`}>
                {c.abbr}
              </div>
              <h3 className="font-display font-bold text-navy text-sm mb-1
                             group-hover:text-ember transition-colors leading-tight">
                {c.title}
              </h3>
              <p className="text-slate-500 text-xs">
                {c.duration} · ₹{(c.price / 1000).toFixed(0)}K
              </p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}