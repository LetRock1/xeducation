import { useState } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { login as loginApi, startSession } from '../utils/api'
import { useAuth } from '../context/AuthContext'
import { tracker } from '../utils/tracker'

export default function Login() {
  const navigate  = useNavigate()
  const location  = useLocation()
  const { login } = useAuth()
  const [form,    setForm]    = useState({ email:'', password:'' })
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const from = location.state?.from || '/'

  async function handle(e) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const r  = await loginApi(form)
      const sid = r.data.session_id
      login(r.data.token, r.data.user, sid)
      tracker.setSession(sid)
      if (!r.data.profile_complete) navigate('/complete-profile', { replace: true })
      else navigate(from, { replace: true })
    } catch(err) { setError(err.response?.data?.detail || 'Login failed') }
    finally { setLoading(false) }
  }

  return (
    <main className="min-h-screen bg-slate-50 pt-20 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-sky-accent to-gold flex items-center justify-center font-display font-black text-navy text-2xl mx-auto mb-4">X</div>
          <h1 className="font-display text-3xl font-extrabold text-navy">Welcome Back</h1>
          <p className="text-slate-500 text-sm mt-1">Continue your learning journey</p>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8">
          <form onSubmit={handle} className="space-y-4">
            <div><label className="lbl">Email Address</label><input type="email" required value={form.email} onChange={e=>setForm(f=>({...f,email:e.target.value}))} placeholder="priya@gmail.com" className="inp"/></div>
            <div><label className="lbl">Password</label><input type="password" required value={form.password} onChange={e=>setForm(f=>({...f,password:e.target.value}))} placeholder="Your password" className="inp"/></div>
            {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}
            <button type="submit" disabled={loading} className="w-full btn-primary mt-2">{loading ? 'Logging in…' : 'Login →'}</button>
          </form>
        </div>

        <p className="text-center text-sm text-slate-500 mt-6">
          New here? <Link to="/signup" className="text-sky-accent hover:underline font-medium">Create an account</Link>
        </p>
      </div>
    </main>
  )
}
