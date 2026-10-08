import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { emailUnsubscribe } from '../utils/api'

// The "Unsubscribe" link in every marketing email: <site>/unsubscribe?t=<email token>.
export default function Unsubscribe() {
  const [params] = useSearchParams()
  const [state, setState] = useState({ busy: true, ok: false, text: '' })

  useEffect(() => {
    const t = params.get('t')
    if (!t) { setState({ busy: false, ok: false, text: 'This unsubscribe link is incomplete.' }); return }
    emailUnsubscribe(t)
      .then(r => setState({ busy: false, ok: true, text: r.data.message }))
      .catch(e => setState({ busy: false, ok: false, text: e.response?.data?.detail || 'This unsubscribe link is not valid any more.' }))
  }, [params])

  return (
    <main className="min-h-screen bg-slate-50 pt-24 pb-16">
      <div className="max-w-md mx-auto px-6">
        <div className="bg-white border border-slate-200 rounded-2xl p-8 text-center">
          <h1 className="font-display text-2xl font-extrabold text-navy mb-3">Email preferences</h1>
          <p className={`text-sm ${state.ok ? 'text-slate-700' : 'text-slate-500'}`}>{state.busy ? 'Updating…' : state.text}</p>
          {!state.busy && <p className="text-slate-500 text-xs mt-4">You can turn emails back on any time in <Link to="/settings" className="text-sky-accent hover:underline">Settings</Link>.</p>}
          <Link to="/" className="inline-block mt-6 text-sky-accent text-sm hover:underline">Back to the website</Link>
        </div>
      </div>
    </main>
  )
}
