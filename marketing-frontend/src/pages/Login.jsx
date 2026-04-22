import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { mktLogin } from '../utils/api'

export default function Login() {
  const navigate = useNavigate()
  const [form,  setForm]  = useState({ email:'', password:'' })
  const [err,   setErr]   = useState('')
  const [busy,  setBusy]  = useState(false)

  async function handle(e) {
    e.preventDefault(); setErr(''); setBusy(true)
    try {
      const r = await mktLogin(form)
      localStorage.setItem('mkt_token', r.data.token)
      navigate('/', { replace: true })
    } catch { setErr('Invalid credentials. Check MARKETING_EMAIL and MARKETING_PASSWORD in your .env') }
    finally { setBusy(false) }
  }

  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <div className="w-full max-w-sm">
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-sky-accent to-gold flex items-center justify-center font-display font-black text-navy text-2xl mx-auto mb-4">X</div>
          <h1 className="font-display text-2xl font-bold text-white">Marketing Dashboard</h1>
          <p className="text-slate-500 text-sm mt-1">X Education — Internal Access Only</p>
        </div>
        <div className="card p-8">
          <form onSubmit={handle} className="space-y-4">
            <div><label className="lbl">Email</label><input type="email" required value={form.email} onChange={e=>setForm(f=>({...f,email:e.target.value}))} placeholder="admin@xeducation.in" className="inp"/></div>
            <div><label className="lbl">Password</label><input type="password" required value={form.password} onChange={e=>setForm(f=>({...f,password:e.target.value}))} placeholder="Marketing password" className="inp"/></div>
            {err && <p className="text-red-400 text-xs bg-red-900/20 border border-red-800/30 rounded-xl px-3 py-2">{err}</p>}
            <button type="submit" disabled={busy} className="w-full btn mt-2">{busy ? 'Signing in…' : 'Enter Dashboard →'}</button>
          </form>
        </div>
      </div>
    </div>
  )
}
