import { useEffect, useState } from 'react'
import { useNavigate }          from 'react-router-dom'
import { getCart, checkout }    from '../utils/api'

export default function Checkout() {
  const navigate = useNavigate()
  const [cart,    setCart]    = useState([])
  const [coupon,  setCoupon]  = useState('')
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')

  useEffect(() => { getCart().then(r => setCart(r.data.cart)).catch(() => {}) }, [])

  const total = cart.reduce((s, i) => s + i.price, 0)

  async function pay() {
    setLoading(true); setError('')
    try {
      const r = await checkout({ coupon_code: coupon || null })
      navigate('/thank-you', { state: { purchased: r.data.courses_purchased, discount: r.data.discount_applied } })
    } catch(e) { setError(e.response?.data?.detail || 'Checkout failed') }
    finally { setLoading(false) }
  }

  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16">
      <div className="max-w-2xl mx-auto px-6 py-8">
        <h1 className="font-display text-3xl font-extrabold text-navy mb-8">Checkout</h1>
        <div className="bg-white border border-slate-200 rounded-2xl p-8 space-y-6">
          {/* Order */}
          <div>
            <h3 className="font-display font-semibold text-navy mb-4">Order Summary</h3>
            {cart.map(i => (
              <div key={i.id} className="flex justify-between text-sm py-2 border-b border-slate-100 last:border-0">
                <span className="text-slate-700">{i.course_title}</span>
                <span className="font-semibold text-navy">₹{i.price.toLocaleString()}</span>
              </div>
            ))}
            <div className="flex justify-between font-bold text-navy text-lg pt-3">
              <span>Total</span>
              <span>₹{total.toLocaleString()}</span>
            </div>
          </div>

          {/* Coupon */}
          <div>
            <label className="lbl">Coupon Code (Optional)</label>
            <div className="flex gap-2">
              <input value={coupon} onChange={e=>setCoupon(e.target.value.toUpperCase())} placeholder="e.g. FUTURE_READY_15" className="inp flex-1 font-mono"/>
            </div>
            <p className="text-slate-400 text-xs mt-1">Coupon codes are sent via email based on your profile and activity.</p>
          </div>

          {/* Payment sim */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
            <p className="font-semibold text-navy text-sm mb-3">Payment Details</p>
            <div className="grid grid-cols-2 gap-3">
              <div><label className="lbl">Card Number</label><input placeholder="4242 4242 4242 4242" className="inp" readOnly/></div>
              <div><label className="lbl">Expiry</label><input placeholder="MM/YY" className="inp" readOnly/></div>
              <div><label className="lbl">CVV</label><input placeholder="•••" className="inp" readOnly/></div>
              <div><label className="lbl">Name on Card</label><input placeholder="Priya Sharma" className="inp" readOnly/></div>
            </div>
            <p className="text-slate-400 text-xs mt-3 text-center">🔒 Simulated payment — no real charges in this demo.</p>
          </div>

          {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}

          <button onClick={pay} disabled={loading || !cart.length} className="w-full btn-primary text-base py-4">
            {loading ? '⏳ Processing…' : `Pay Now — ₹${total.toLocaleString()}`}
          </button>
        </div>
      </div>
    </main>
  )
}
