import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { completeProfile } from '../utils/api'
import { useAuth } from '../context/AuthContext'

const OCCUPATIONS    = ['Working Professional','Student','Unemployed','Businessman','Housewife','Other']
const SPECIALIZATIONS= ['Finance Management','Human Resource Management','Marketing Management','Operations Management','IT Projects Management','Supply Chain Management','Banking, Investment And Insurance','Travel and Tourism','Media and Advertising','Business Administration','E-Commerce','Retail Management','Healthcare Management','International Business','Services Excellence']
const AGE_BRACKETS   = ['18-24','25-30','31-35','36-45','46+']
const CITIES         = ['Mumbai','Pune','Delhi','Bangalore','Hyderabad','Chennai','Kolkata','Ahmedabad','Jaipur','Surat','Lucknow','Nagpur','Other']
const HOW_HEARD      = ['Online Search','Word of Mouth','Social Media Ad','Friend/Colleague Referral','Email Newsletter','Webinar/Event','Other Website']

export default function CompleteProfile() {
  const navigate = useNavigate()
  const { user, refreshProfile } = useAuth()
  const [form, setForm] = useState({ current_occupation:'', specialization:'', age_bracket:'', city:'', country:'India', how_did_you_hear:'' })
  const [loading, setLoading] = useState(false)
  const [error,   setError]   = useState('')
  const set = (k,v) => setForm(f=>({...f,[k]:v}))
  const sel = 'w-full border border-slate-200 rounded-xl px-4 py-3 text-sm focus:outline-none focus:border-sky-accent bg-white'

  async function submit(e) {
    e.preventDefault()
    if (!form.current_occupation || !form.specialization) { setError('Occupation and Specialization are required.'); return }
    setLoading(true); setError('')
    try {
      await completeProfile(form)
      refreshProfile()
      navigate('/', { replace: true })
    } catch(err) { setError(err.response?.data?.detail || 'Failed to save profile') }
    finally { setLoading(false) }
  }

  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16 flex items-center justify-center px-4">
      <div className="w-full max-w-lg">
        <div className="text-center mb-8 pt-6">
          <div className="text-5xl mb-4">🎯</div>
          <h1 className="font-display text-3xl font-extrabold text-navy mb-2">
            Welcome, {user?.name?.split(' ')[0]}!
          </h1>
          <p className="text-slate-500 text-sm max-w-sm mx-auto">
            Tell us a little about yourself so we can personalise your course recommendations and learning journey.
          </p>
        </div>

        <div className="bg-white border border-slate-200 rounded-2xl shadow-sm p-8">
          <form onSubmit={submit} className="space-y-5">
            <div>
              <label className="lbl">Current Occupation *</label>
              <select value={form.current_occupation} onChange={e=>set('current_occupation',e.target.value)} required className={sel}>
                <option value="">Select your occupation</option>
                {OCCUPATIONS.map(o=><option key={o}>{o}</option>)}
              </select>
            </div>
            <div>
              <label className="lbl">Your Industry / Specialization *</label>
              <select value={form.specialization} onChange={e=>set('specialization',e.target.value)} required className={sel}>
                <option value="">Select your specialization</option>
                {SPECIALIZATIONS.map(s=><option key={s}>{s}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="lbl">Age Bracket</label>
                <select value={form.age_bracket} onChange={e=>set('age_bracket',e.target.value)} className={sel}>
                  <option value="">Prefer not to say</option>
                  {AGE_BRACKETS.map(a=><option key={a}>{a}</option>)}
                </select>
              </div>
              <div>
                <label className="lbl">City</label>
                <select value={form.city} onChange={e=>set('city',e.target.value)} className={sel}>
                  <option value="">Select city</option>
                  {CITIES.map(c=><option key={c}>{c}</option>)}
                </select>
              </div>
            </div>
            <div>
              <label className="lbl">How Did You Hear About Us?</label>
              <select value={form.how_did_you_hear} onChange={e=>set('how_did_you_hear',e.target.value)} className={sel}>
                <option value="">Select source</option>
                {HOW_HEARD.map(h=><option key={h}>{h}</option>)}
              </select>
            </div>

            {error && <p className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-xl px-3 py-2">⚠️ {error}</p>}

            <button type="submit" disabled={loading} className="w-full btn-primary mt-2">
              {loading ? 'Saving…' : 'Save & Explore Courses →'}
            </button>
            <button type="button" onClick={() => navigate('/', { replace:true })}
              className="w-full text-slate-400 text-sm hover:text-slate-600">
              Skip for now (you can complete this later)
            </button>
          </form>
        </div>
        <p className="text-center text-xs text-slate-400 mt-4">
          🔒 Your data is used only to personalise your experience. Never shared with third parties.
        </p>
      </div>
    </main>
  )
}
