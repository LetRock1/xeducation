import { useEffect, useState } from 'react'
import { Link, useNavigate }   from 'react-router-dom'
import { getWishlist, removeFromWishlist, addToCart } from '../utils/api'

export default function Wishlist() {
  const navigate  = useNavigate()
  const [items,   setItems]   = useState([])
  const [loading, setLoading] = useState(true)
  const [msgs,    setMsgs]    = useState({})

  const load = () =>
    getWishlist()
      .then(r => setItems(r.data.wishlist))
      .catch(() => {})
      .finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  async function remove(slug) {
    await removeFromWishlist(slug).catch(() => {})
    load()
  }

  async function moveToCart(item) {
    try {
      await addToCart({ course_slug: item.course_slug, course_title: item.course_title, price: 0 })
      await removeFromWishlist(item.course_slug)
      setMsgs(p => ({ ...p, [item.course_slug]: 'Moved to cart' }))
      load()
    } catch (e) {
      setMsgs(p => ({ ...p, [item.course_slug]: e.response?.data?.detail || 'Error' }))
    }
  }

  if (loading) return (
    <div className="min-h-screen pt-24 flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin" />
    </div>
  )

  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16">
      <div className="max-w-4xl mx-auto px-6 py-8">

        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display text-3xl font-extrabold text-navy">Saved Courses</h1>
            <p className="text-slate-500 text-sm mt-1">{items.length} course{items.length !== 1 ? 's' : ''} saved</p>
          </div>
          <Link to="/courses"
            className="text-sm text-slate-500 border border-slate-200 px-4 py-2 rounded-xl hover:border-navy hover:text-navy transition-all">
            Browse More
          </Link>
        </div>

        {!items.length ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-16 text-center">
            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-5">
              <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/>
              </svg>
            </div>
            <p className="font-display font-bold text-navy text-lg mb-2">No saved courses yet</p>
            <p className="text-slate-500 text-sm mb-6">
              Browse courses and click "Save" on any course page to add it here.
            </p>
            <Link to="/courses"
              className="inline-block bg-ember hover:bg-orange-600 text-white font-semibold px-6 py-3 rounded-xl transition-all">
              Browse Courses
            </Link>
          </div>
        ) : (
          <div className="space-y-4">
            {items.map(item => (
              <div key={item.id}
                className="bg-white border border-slate-200 rounded-2xl p-5 flex items-center gap-5">
                {/* Course indicator */}
                <div className="w-12 h-12 rounded-xl bg-navy flex items-center justify-center flex-shrink-0">
                  <span className="text-sky-accent font-display font-bold text-sm">
                    {item.course_title?.split(' ').map(w => w[0]).join('').slice(0, 3)}
                  </span>
                </div>

                {/* Info */}
                <div className="flex-1 min-w-0">
                  <h3 className="font-display font-bold text-navy">{item.course_title}</h3>
                  <p className="text-slate-400 text-xs mt-0.5">
                    Saved on {new Date(item.added_at).toLocaleDateString('en-IN', { day:'numeric', month:'short', year:'numeric' })}
                  </p>
                  {msgs[item.course_slug] && (
                    <p className="text-green-600 text-xs mt-1">{msgs[item.course_slug]}</p>
                  )}
                </div>

                {/* Actions */}
                <div className="flex items-center gap-3 flex-shrink-0">
                  <Link to={`/courses/${item.course_slug}`}
                    className="text-sm text-slate-600 border border-slate-200 px-4 py-2 rounded-lg hover:border-navy hover:text-navy transition-all">
                    View
                  </Link>
                  <button onClick={() => moveToCart(item)}
                    className="text-sm bg-ember hover:bg-orange-600 text-white px-4 py-2 rounded-lg transition-all">
                    Add to Cart
                  </button>
                  <button onClick={() => remove(item.course_slug)}
                    className="p-2 text-slate-300 hover:text-red-500 transition-colors rounded-lg hover:bg-red-50"
                    title="Remove from wishlist">
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </main>
  )
}