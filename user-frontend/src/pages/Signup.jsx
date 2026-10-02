import { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { signup, verifyOtp, resendOtp } from '../utils/api'
import { useAuth } from '../context/AuthContext'
import { tracker } from '../utils/tracker'

export default function Signup() {
  const navigate = useNavigate()
  const location = useLocation()
  const { login } = useAuth()
  const [step,    setStep]  = useState(location.state?.step === 'otp' ? 'otp' : 'form') // form | otp
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const [form,    setForm]    = useState({ name:'', email: location.state?.email || '', password:'' })
  const [otp,     setOtp]     = useState('')
  const [cooldown, setCooldown] = useState(step === 'otp' ? 60 : 0)
  const [info,    setInfo]    = useState('')

  useEffect(() => {
    if (cooldown <= 0) return
    const t = setTimeout(() => setCooldown(c => c - 1), 1000)
    return () => clearTimeout(t)
  }, [cooldown])

  async function handleResend() {
    setError(''); setInfo('')
    try {
      const r = await resendOtp(form.email)
      setInfo(r.data.message); setCooldown(60)
    } catch (err) { setError(err.response?.data?.detail || 'Could not resend the code') }
  }

  const set = (k,v) => setForm(f=>({...f,[k]:v}))

  async function handleSignup(e) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      await signup(form)
      setStep('otp'); setCooldown(60)
    } catch(err) { setError(err.response?.data?.detail || 'Signup failed') }
    finally { setLoading(false) }
  }

  async function handleVerify(e) {
    e.preventDefault(); setError(''); setLoading(true)
    try {
      const r = await verifyOtp({ email: form.email, otp })
      login(r.data.token, r.data.user, r.data.session_id || null)
      tracker.newSession()
      navigate(r.data.profile_complete ? '/' : '/complete-profile', { replace: true })
    } catch(err) { setError(err.response?.data?.detail || 'Invalid OTP') }
    finally { setLoading(false) }
  }

  return (
    <main className="min-h-screen bg-slate-50 pt-20 flex items-center justify-center px-4 relative overflow-hidden">
      <div className="pointer-events-none absolute -top-32 -right-32 w-96 h-96 bg-sky-accent/10 rounded-full blur-3xl"/>
      <div className="pointer-events-none absolute -bottom-32 -left-32 w-96 h-96 bg-gold/10 rounded-full blur-3xl"/>

      <div className="w-full max-w-md relative">
        <div className="text-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-gradient-to-br from-sky-accent to-gold flex items-center justify-center font-display font-black text-navy text-2xl mx-auto mb-4 shadow-lg shadow-sky-accent/20">X</div>
          <h1 className="font-display text-3xl font-extrabold text-navy">{step==='form' ? 'Create Account' : 'Verify Email'}</h1>
          <p className="text-slate-500 text-sm mt-1">
            {step==='form' ? 'Join 500,000+ learners transforming their careers' : `Enter the 6-digit OTP sent to ${form.email}`}
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm hover:shadow-md transition-shadow p-8">
          {step === 'form' ? (
            <form onSubmit={handleSignup} className="space-y-4">
              <div><label className="lbl">Full Name *</label><input required value={form.name} onChange={e=>set('name',e.target.value)} placeholder="Priya Sharma" className="inp"/></div>
              <div><label className="lbl">Email Address *</label><input type="email" required value={form.email} onChange={e=>set('email',e.target.value)} placeholder="priya@gmail.com" className="inp"/></div>
              <div><label className="lbl">Password *</label><input type="password" required minLength={6} value={form.password} onChange={e=>set('password',e.target.value)} placeholder="Min 6 characters" className="inp"/></div>
              {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}
              <button type="submit" disabled={loading} className="w-full btn-primary mt-2">{loading ? 'Sending OTP…' : 'Create Account →'}</button>
            </form>
          ) : (
            <form onSubmit={handleVerify} className="space-y-4">
              <div>
                <label className="lbl">6-Digit OTP</label>
                <input required value={otp} onChange={e=>setOtp(e.target.value)} placeholder="Enter OTP from email" maxLength={6} className="inp text-center text-2xl font-bold tracking-[0.5em]"/>
              </div>
              <p className="text-slate-400 text-xs text-center">OTP expires in 10 minutes. Check your spam folder if not received.</p>
              {info && <p className="text-green-700 text-sm bg-green-50 border border-green-200 rounded-xl px-3 py-2">{info}</p>}
              <button type="button" onClick={handleResend} disabled={cooldown > 0}
                className="w-full text-sm text-sky-accent hover:underline disabled:text-slate-400 disabled:no-underline">
                {cooldown > 0 ? `Resend code in ${cooldown}s` : 'Resend code'}
              </button>
              {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}
              <button type="submit" disabled={loading} className="w-full btn-primary">{loading ? 'Verifying…' : 'Verify & Continue →'}</button>
              <button type="button" onClick={() => { setStep('form'); setError('') }} className="w-full text-slate-500 text-sm hover:text-navy">← Change email</button>
            </form>
          )}
        </div>

        <p className="text-center text-sm text-slate-500 mt-6">
          Already have an account? <Link to="/login" className="text-sky-accent hover:underline font-medium">Login</Link>
        </p>
      </div>
    </main>
  )
}
