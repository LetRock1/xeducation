import { useEffect, useState, useRef } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { getCart, checkout, checkoutStart, checkCoupon, getCoupons } from '../utils/api'
import { tracker } from '../utils/tracker'

// Luhn check — catches typos in card numbers (payments are simulated, nothing is charged)
function luhnOk(num) {
  const d = num.replace(/\D/g, '')
  if (d.length < 12) return false
  let sum = 0, alt = false
  for (let i = d.length - 1; i >= 0; i--) {
    let n = +d[i]
    if (alt) { n *= 2; if (n > 9) n -= 9 }
    sum += n; alt = !alt
  }
  return sum % 10 === 0
}

export default function Checkout() {
  const navigate = useNavigate()
  const [cart, setCart] = useState([])
  const [ready, setReady] = useState(false)
  const [coupons, setCoupons] = useState([])
  const [code, setCode] = useState('')
  const [applied, setApplied] = useState(null)        // response of /coupons/check
  const [couponMsg, setCouponMsg] = useState('')
  const [method, setMethod] = useState('upi')
  const [pay, setPay] = useState({ upi: '', card: '', expiry: '', cvv: '', name: '' })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const started = useRef(false)

  useEffect(() => {
    getCart().then(r => setCart(r.data.cart)).catch(() => {}).finally(() => setReady(true))
    getCoupons().then(r => setCoupons((r.data.coupons || []).filter(c => !c.used && (!c.expires_at || new Date(c.expires_at.replace(' ', 'T')) > new Date())))).catch(() => {})
  }, [])

  useEffect(() => {
    if (started.current) return
    started.current = true
    checkoutStart().catch(() => {})
    tracker.checkoutStart()
  }, [])

  const subtotal = cart.reduce((s, i) => s + i.price, 0)
  const total = applied ? applied.total : subtotal

  async function apply(c) {
    const value = (c ?? code).trim().toUpperCase()
    if (!value) return
    setCouponMsg(''); setCode(value)
    try {
      const r = await checkCoupon(value)
      setApplied(r.data); setCouponMsg(`✅ ${r.data.discount_pct}% off applied`)
    } catch (e) { setApplied(null); setCouponMsg('⚠️ ' + (e.response?.data?.detail || 'Invalid code')) }
  }

  function paymentError() {
    if (method === 'upi') return /^[\w.-]{2,}@[a-z]{2,}$/i.test(pay.upi) ? '' : 'Enter a UPI ID like name@okbank.'
    if (!luhnOk(pay.card)) return 'Card number looks wrong (try the test card 4242 4242 4242 4242).'
    if (!/^(0[1-9]|1[0-2])\/\d{2}$/.test(pay.expiry)) return 'Expiry must be MM/YY.'
    if (!/^\d{3,4}$/.test(pay.cvv)) return 'CVV must be 3 or 4 digits.'
    if (!pay.name.trim()) return 'Enter the name on the card.'
    return ''
  }

  async function placeOrder() {
    const pErr = paymentError()
    if (pErr) { setError(pErr); return }
    setLoading(true); setError('')
    try {
      const r = await checkout({ coupon_code: applied?.code || null })
      navigate('/thank-you', { state: { purchased: r.data.courses_purchased, discount: r.data.discount_applied } })
    } catch (e) { setError(e.response?.data?.detail || 'Checkout failed') }
    finally { setLoading(false) }
  }

  if (!ready) return <main className="min-h-screen pt-28 text-center text-slate-500">Loading…</main>
  if (!cart.length) return (
    <main className="min-h-screen bg-slate-50 pt-28 text-center">
      <p className="text-slate-600 mb-4">Your cart is empty.</p>
      <Link to="/courses" className="btn-primary">Browse courses</Link>
    </main>
  )

  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16">
      <div className="max-w-2xl mx-auto px-6 py-8">
        <h1 className="font-display text-3xl font-extrabold text-navy mb-8">Checkout</h1>
        <div className="bg-white border border-slate-200 rounded-2xl p-8 space-y-6">
          <div>
            <h3 className="font-display font-semibold text-navy mb-4">Order summary</h3>
            {cart.map(i => (
              <div key={i.id} className="flex justify-between text-sm py-2 border-b border-slate-100 last:border-0">
                <span className="text-slate-700">{i.course_title}</span>
                <span className="font-semibold text-navy">₹{i.price.toLocaleString()}</span>
              </div>
            ))}
            {applied && (
              <div className="flex justify-between text-sm py-2 text-green-700">
                <span>Coupon {applied.code} ({applied.discount_pct}% off)</span><span>−₹{applied.discount.toLocaleString()}</span>
              </div>
            )}
            <div className="flex justify-between font-bold text-navy text-lg pt-3">
              <span>Total</span><span>₹{total.toLocaleString()}</span>
            </div>
          </div>

          <div>
            <label className="lbl">Coupon code</label>
            <div className="flex gap-2">
              <input value={code} onChange={e => setCode(e.target.value.toUpperCase())} placeholder="Enter code" className="inp flex-1 font-mono" />
              <button type="button" onClick={() => apply()} className="btn-outline px-4 py-2 text-sm">Apply</button>
            </div>
            {couponMsg && <p className={`text-xs mt-1 ${couponMsg.startsWith('✅') ? 'text-green-700' : 'text-red-500'}`}>{couponMsg}</p>}
            {coupons.length > 0 && !applied && (
              <div className="flex flex-wrap gap-2 mt-2">
                <span className="text-xs text-slate-500">Your offers:</span>
                {coupons.map(c => (
                  <button key={c.id} type="button" onClick={() => apply(c.coupon_code)}
                    className="text-xs font-mono border border-amber-300 bg-amber-50 text-amber-800 rounded-full px-2.5 py-0.5 hover:bg-amber-100">
                    {c.coupon_code} · {c.discount_pct}%
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4">
            <div className="flex gap-2 mb-4">
              {[['upi', 'UPI'], ['card', 'Card']].map(([k, l]) => (
                <button key={k} type="button" onClick={() => { setMethod(k); setError('') }}
                  className={`px-4 py-1.5 rounded-lg text-sm font-semibold border ${method === k ? 'bg-navy text-white border-navy' : 'border-slate-300 text-slate-600'}`}>{l}</button>
              ))}
            </div>
            {method === 'upi' ? (
              <div><label className="lbl">UPI ID</label>
                <input className="inp" placeholder="name@okbank" value={pay.upi} onChange={e => setPay(p => ({ ...p, upi: e.target.value }))} /></div>
            ) : (
              <div className="grid grid-cols-2 gap-3">
                <div className="col-span-2"><label className="lbl">Card number</label>
                  <input className="inp" inputMode="numeric" placeholder="4242 4242 4242 4242" value={pay.card} onChange={e => setPay(p => ({ ...p, card: e.target.value }))} /></div>
                <div><label className="lbl">Expiry</label><input className="inp" placeholder="MM/YY" value={pay.expiry} onChange={e => setPay(p => ({ ...p, expiry: e.target.value }))} /></div>
                <div><label className="lbl">CVV</label><input className="inp" placeholder="123" value={pay.cvv} onChange={e => setPay(p => ({ ...p, cvv: e.target.value }))} /></div>
                <div className="col-span-2"><label className="lbl">Name on card</label><input className="inp" value={pay.name} onChange={e => setPay(p => ({ ...p, name: e.target.value }))} /></div>
              </div>
            )}
            <p className="text-slate-400 text-xs mt-3 text-center">🔒 Simulated payment for this project — no money is charged.</p>
          </div>

          {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}
          <button onClick={placeOrder} disabled={loading} className="w-full btn-primary text-base py-4">
            {loading ? '⏳ Processing…' : `Pay ₹${total.toLocaleString()}`}
          </button>
        </div>
      </div>
    </main>
  )
}
