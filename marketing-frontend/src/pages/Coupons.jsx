import { useEffect, useState } from 'react'
import { getAllCoupons, deleteCoupon } from '../utils/api'

export default function Coupons() {
  const [coupons,  setCoupons]  = useState([])
  const [loading,  setLoading]  = useState(true)
  const [deleting, setDeleting] = useState(null)

  const load = () =>
    getAllCoupons()
      .then(r => setCoupons(r.data.coupons))
      .catch(() => {})
      .finally(() => setLoading(false))

  useEffect(() => { load() }, [])

  async function remove(id) {
    if (!window.confirm('Delete this coupon? This cannot be undone.')) return
    setDeleting(id)
    try {
      await deleteCoupon(id)
      load()
    } catch {
      alert('Failed to delete coupon.')
    } finally {
      setDeleting(null)
    }
  }

  const tierLabel = t =>
    t === 'Nurture via Email/WhatsApp' ? 'Nurture'
    : t === 'Marketing Campaign' ? 'Campaign'
    : t === 'Target Immediately' ? 'Target Now'
    : t

  const active  = coupons.filter(c => !c.used).length
  const used    = coupons.filter(c =>  c.used).length

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="font-display text-2xl font-bold text-white">Coupons Issued</h1>
          <p className="text-slate-500 text-sm mt-1">
            {coupons.length} total · {active} active · {used} used
          </p>
        </div>
      </div>

      <div className="card overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-white/10 text-xs text-slate-500 uppercase tracking-wide">
                {['Lead', 'Code', 'Discount', 'Tier', 'Status', 'Issued', 'Expires', ''].map(h => (
                  <th key={h} className="px-4 py-3 font-semibold text-left">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {loading ? (
                <tr>
                  <td colSpan={8} className="text-center py-12 text-slate-500">
                    Loading coupons…
                  </td>
                </tr>
              ) : !coupons.length ? (
                <tr>
                  <td colSpan={8} className="text-center py-12 text-slate-500">
                    No coupons issued yet. Generate one from a lead's detail page.
                  </td>
                </tr>
              ) : (
                coupons.map(c => (
                  <tr key={c.id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-4 py-3.5">
                      <p className="text-white font-medium">{c.name}</p>
                      <p className="text-slate-500 text-xs">{c.email}</p>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="font-mono text-ember font-bold">{c.coupon_code}</span>
                    </td>
                    <td className="px-4 py-3.5">
                      <span className="text-green-400 font-bold">{c.discount_pct}% off</span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-400 text-xs">
                      {tierLabel(c.tier)}
                    </td>
                    <td className="px-4 py-3.5">
                      <span className={`text-xs px-2.5 py-1 rounded-full font-medium ${
                        c.used
                          ? 'bg-slate-800 text-slate-500'
                          : 'bg-green-900/30 text-green-400'}`}>
                        {c.used ? 'Used' : 'Active'}
                      </span>
                    </td>
                    <td className="px-4 py-3.5 text-slate-500 text-xs">
                      {c.created_at?.slice(0, 10) || '—'}
                    </td>
                    <td className="px-4 py-3.5 text-slate-500 text-xs">
                      {c.expires_at?.slice(0, 10) || '—'}
                    </td>
                    <td className="px-4 py-3.5">
                      <button
                        onClick={() => remove(c.id)}
                        disabled={deleting === c.id}
                        className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-900/20
                                   rounded-lg transition-all disabled:opacity-50"
                        title="Delete coupon">
                        {deleting === c.id ? (
                          <div className="w-4 h-4 border-2 border-slate-500 border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                          </svg>
                        )}
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}