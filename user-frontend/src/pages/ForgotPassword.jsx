import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { forgotPassword, resetPassword } from '../utils/api'

export default function ForgotPassword() {
  const navigate = useNavigate()
  const [step, setStep] = useState('email')       // email | reset
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [pw, setPw] = useState('')
  const [pw2, setPw2] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [info, setInfo] = useState('')

  async function sendCode(e) {
    e.preventDefault(); setError(''); setInfo(''); setLoading(true)
    try {
      const r = await forgotPassword(email)
      setInfo(r.data.message); setStep('reset')
    } catch (err) { setError(err.response?.data?.detail || 'Could not send the code') }
    finally { setLoading(false) }
  }

  async function reset(e) {
    e.preventDefault(); setError('')
    if (pw !== pw2) { setError("Passwords don't match."); return }
    setLoading(true)
    try {
      await resetPassword({ email, otp, new_password: pw })
      navigate('/login', { replace: true, state: { message: 'Password updated — please log in.' } })
    } catch (err) { setError(err.response?.data?.detail || 'Could not reset the password') }
    finally { setLoading(false) }
  }

  return (
    <main className="min-h-screen bg-slate-50 pt-20 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="font-display text-3xl font-extrabold text-navy">Reset your password</h1>
          <p className="text-slate-500 text-sm mt-1">
            {step === 'email' ? "We'll email you a 6-digit code." : `Enter the code sent to ${email} and choose a new password.`}
          </p>
        </div>
        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8">
          {step === 'email' ? (
            <form onSubmit={sendCode} className="space-y-4">
              <div><label className="lbl">Email Address</label>
                <input type="email" required value={email} onChange={e => setEmail(e.target.value)} className="inp" placeholder="you@example.com" /></div>
              {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}
              <button disabled={loading} className="w-full btn-primary">{loading ? 'Sending…' : 'Send reset code'}</button>
            </form>
          ) : (
            <form onSubmit={reset} className="space-y-4">
              {info && <p className="text-green-700 text-sm bg-green-50 border border-green-200 rounded-xl px-3 py-2">{info}</p>}
              <div><label className="lbl">6-digit code</label>
                <input required maxLength={6} value={otp} onChange={e => setOtp(e.target.value)} className="inp text-center text-xl font-bold tracking-[0.4em]" /></div>
              <div><label className="lbl">New password</label>
                <input type="password" required minLength={6} value={pw} onChange={e => setPw(e.target.value)} className="inp" placeholder="Min 6 characters" /></div>
              <div><label className="lbl">Confirm new password</label>
                <input type="password" required minLength={6} value={pw2} onChange={e => setPw2(e.target.value)} className="inp" /></div>
              {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}
              <button disabled={loading} className="w-full btn-primary">{loading ? 'Saving…' : 'Set new password'}</button>
              <button type="button" onClick={() => setStep('email')} className="w-full text-slate-500 text-sm hover:text-navy">← Use a different email</button>
            </form>
          )}
        </div>
        <p className="text-center text-sm text-slate-500 mt-6"><Link to="/login" className="text-sky-accent hover:underline">Back to login</Link></p>
      </div>
    </main>
  )
}
