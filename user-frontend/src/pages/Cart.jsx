import { useEffect, useState } from 'react'
import { Link, useNavigate }   from 'react-router-dom'
import { getCart, removeFromCart } from '../utils/api'

export default function Cart() {
  const navigate  = useNavigate()
  const [cart,    setCart]    = useState([])
  const [loading, setLoading] = useState(true)
  const [removing,setRemoving]= useState(null)

  const load = () =>
    getCart()
      .then(r => setCart(r.data.cart))
      .catch(() => {})
      .finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  async function remove(slug) {
    setRemoving(slug)
    await removeFromCart(slug).catch(() => {})
    await load()
    setRemoving(null)
  }

  const total = cart.reduce((s, i) => s + i.price, 0)

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
            <h1 className="font-display text-3xl font-extrabold text-navy">Cart</h1>
            <p className="text-slate-500 text-sm mt-1">
              {cart.length} item{cart.length !== 1 ? 's' : ''}
            </p>
          </div>
          <Link to="/courses"
            className="text-sm text-slate-500 border border-slate-200 px-4 py-2 rounded-xl
                       hover:border-navy hover:text-navy transition-all">
            Continue Shopping
          </Link>
        </div>

        {!cart.length ? (
          <div className="bg-white border border-slate-200 rounded-2xl p-16 text-center">
            <div className="w-16 h-16 bg-slate-100 rounded-full flex items-center justify-center mx-auto mb-5">
              <svg className="w-8 h-8 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                  d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"/>
              </svg>
            </div>
            <p className="font-display font-bold text-navy text-lg mb-2">Your cart is empty</p>
            <p className="text-slate-500 text-sm mb-6">Add courses to proceed to checkout.</p>
            <Link to="/courses"
              className="inline-block bg-ember hover:bg-orange-600 text-white font-semibold px-6 py-3 rounded-xl transition-all">
              Browse Courses
            </Link>
          </div>
        ) : (
          <div className="grid md:grid-cols-3 gap-6">

            {/* Cart items */}
            <div className="md:col-span-2 space-y-3">
              {cart.map(item => (
                <div key={item.id}
                  className="bg-white border border-slate-200 rounded-2xl px-5 py-4
                             flex items-center gap-4">
                  {/* Course abbreviation box */}
                  <div className="w-12 h-12 rounded-xl bg-navy flex items-center
                                  justify-center flex-shrink-0">
                    <span className="text-sky-accent font-display font-bold text-xs">
                      {item.course_title.split(' ').map(w => w[0]).join('').slice(0, 3)}
                    </span>
                  </div>

                  <div className="flex-1 min-w-0">
                    <h3 className="font-display font-bold text-navy text-sm">{item.course_title}</h3>
                    <p className="text-slate-400 text-xs mt-0.5">
                      Added {new Date(item.added_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                    </p>
                  </div>

                  <p className="font-bold text-ember text-base flex-shrink-0">
                    ₹{item.price.toLocaleString()}
                  </p>

                  <button
                    onClick={() => remove(item.course_slug)}
                    disabled={removing === item.course_slug}
                    className="p-2 text-slate-300 hover:text-red-500 hover:bg-red-50
                               rounded-lg transition-all disabled:opacity-50"
                    title="Remove from cart">
                    {removing === item.course_slug ? (
                      <div className="w-4 h-4 border-2 border-slate-300 border-t-transparent rounded-full animate-spin" />
                    ) : (
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12"/>
                      </svg>
                    )}
                  </button>
                </div>
              ))}
            </div>

            {/* Summary */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 h-fit space-y-4">
              <h3 className="font-display font-bold text-navy">Order Summary</h3>

              <div className="space-y-2 text-sm">
                {cart.map(i => (
                  <div key={i.id} className="flex justify-between text-slate-600">
                    <span className="truncate mr-2 max-w-[140px]">{i.course_title}</span>
                    <span className="flex-shrink-0">₹{i.price.toLocaleString()}</span>
                  </div>
                ))}
              </div>

              <div className="border-t border-slate-100 pt-3 flex justify-between
                              font-bold text-navy text-base">
                <span>Total</span>
                <span>₹{total.toLocaleString()}</span>
              </div>

              <p className="text-green-700 text-xs bg-green-50 border border-green-100
                            rounded-lg px-3 py-2">
                Have a coupon? Apply it at checkout for a discount.
              </p>

              <button onClick={() => navigate('/checkout')}
                className="w-full bg-ember hover:bg-orange-600 text-white font-bold py-3
                           rounded-xl transition-all active:scale-95">
                Proceed to Checkout
              </button>

              <Link to="/courses"
                className="block text-center text-slate-400 text-sm hover:text-slate-600 transition-colors">
                Continue Shopping
              </Link>
            </div>
          </div>
        )}
      </div>
    </main>
  )
}