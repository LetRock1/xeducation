import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getRecommendations } from '../utils/api'
import { getCourseBySlug } from '../data/courses'

export default function RecommendedCourses() {
  const [recs, setRecs] = useState([])
  useEffect(() => {
    getRecommendations()
      .then(r => {
        const titles = r.data.recommendations
        const slugMap = {
          'Data Science & Analytics':'data-science-analytics',
          'Digital Marketing':'digital-marketing',
          'MBA Core':'mba-core',
          'Supply Chain Management':'supply-chain-management',
          'HR Management':'hr-management',
          'Finance & Banking':'finance-banking',
          'Operations Management':'operations-management',
          'E-Commerce':'e-commerce',
        }
        const courses = titles.map(t => getCourseBySlug(slugMap[t])).filter(Boolean)
        setRecs(courses)
      })
      .catch(() => {})
  }, [])

  if (!recs.length) return null
  return (
    <section className="py-10 px-6 max-w-7xl mx-auto">
      <h2 className="font-display text-xl font-bold text-navy mb-6">
        🎯 Recommended for You
      </h2>
      <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {recs.map(c => (
          <Link key={c.id} to={`/courses/${c.slug}`}
            className="group card-hover bg-white border border-slate-200 rounded-2xl overflow-hidden">
            <div className={`h-1.5 bg-gradient-to-r ${c.color}`}/>
            <div className="p-4">
              <span className="text-2xl">{c.icon}</span>
              <h3 className="font-display font-bold text-navy text-sm mt-2 mb-1 group-hover:text-ember transition-colors">{c.title}</h3>
              <p className="text-slate-500 text-xs">{c.duration} · ₹{(c.price/1000).toFixed(0)}K</p>
            </div>
          </Link>
        ))}
      </div>
    </section>
  )
}
