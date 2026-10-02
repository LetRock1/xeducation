import { useEffect, useState } from 'react'
import { completeProfile, updatePrefs, changePassword } from '../utils/api'
import { useAuth } from '../context/AuthContext'
import { OCCUPATIONS, SPECIALIZATIONS, AGE_BRACKETS, CITIES, COUNTRIES, HOW_HEARD } from '../data/profileOptions'

function Notice({ msg }) {
  if (!msg) return null
  const ok = !msg.startsWith('⚠️')
  return <p className={`text-sm rounded-xl px-3 py-2 border ${ok ? 'text-green-700 bg-green-50 border-green-200' : 'text-red-600 bg-red-50 border-red-200'}`}>{msg}</p>
}

function Toggle({ checked, onChange, label, hint }) {
  return (
    <label className="flex items-start gap-3 py-3 border-b border-slate-100 last:border-0 cursor-pointer">
      <input type="checkbox" checked={checked} onChange={e => onChange(e.target.checked)} className="mt-1 w-4 h-4 accent-orange-500" />
      <span>
        <span className="block text-sm font-medium text-navy">{label}</span>
        <span className="block text-xs text-slate-500">{hint}</span>
      </span>
    </label>
  )
}

export default function Settings() {
  const { user, profile, refreshProfile } = useAuth()
  const [form, setForm] = useState({ current_occupation: '', specialization: '', age_bracket: '', city: '', country: 'India', how_did_you_hear: '' })
  const [prefs, setPrefs] = useState({ email: true, calls: true, whatsapp: false, phone: '' })
  const [pw, setPw] = useState({ current_password: '', new_password: '', confirm: '' })
  const [msgs, setMsgs] = useState({})
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  useEffect(() => {
    if (!profile) return
    setForm({
      current_occupation: profile.current_occupation || '', specialization: profile.specialization || '',
      age_bracket: profile.age_bracket || '', city: profile.city && profile.city !== 'Unknown' ? profile.city : '',
      country: profile.country || 'India', how_did_you_hear: profile.how_did_you_hear && profile.how_did_you_hear !== 'Unknown' ? profile.how_did_you_hear : '',
    })
    setPrefs({ email: profile.do_not_email !== 'Yes', calls: profile.do_not_call !== 'Yes', whatsapp: !!profile.whatsapp_opt_in, phone: profile.phone || '' })
  }, [profile])

  const note = (k, m) => setMsgs(x => ({ ...x, [k]: m }))

  async function saveProfile(e) {
    e.preventDefault()
    if (!form.current_occupation || !form.specialization) { note('profile', '⚠️ Occupation and specialization are required.'); return }
    try { await completeProfile(form); refreshProfile(); note('profile', 'Profile saved.') }
    catch (err) { note('profile', '⚠️ ' + (err.response?.data?.detail || 'Could not save')) }
  }

  async function savePrefs(e) {
    e.preventDefault()
    try {
      await updatePrefs({ do_not_email: !prefs.email, do_not_call: !prefs.calls, whatsapp_opt_in: prefs.whatsapp, phone: prefs.phone })
      refreshProfile(); note('prefs', 'Communication preferences saved.')
    } catch (err) { note('prefs', '⚠️ ' + (err.response?.data?.detail || 'Could not save')) }
  }

  async function savePassword(e) {
    e.preventDefault()
    if (pw.new_password !== pw.confirm) { note('pw', "⚠️ New passwords don't match."); return }
    try {
      await changePassword({ current_password: pw.current_password, new_password: pw.new_password })
      setPw({ current_password: '', new_password: '', confirm: '' }); note('pw', 'Password changed.')
    } catch (err) { note('pw', '⚠️ ' + (err.response?.data?.detail || 'Could not change password')) }
  }

  const sel = 'inp'
  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16">
      <div className="max-w-3xl mx-auto px-6 py-8 space-y-6">
        <div>
          <h1 className="font-display text-3xl font-extrabold text-navy">Settings</h1>
          <p className="text-slate-500 text-sm mt-1">{user?.email}</p>
        </div>

        <form onSubmit={saveProfile} className="bg-white border border-slate-200 rounded-2xl p-6 space-y-4">
          <h2 className="font-display font-bold text-navy">Your profile</h2>
          <p className="text-slate-500 text-xs -mt-2">Used to recommend courses that fit your background.</p>
          <div className="grid sm:grid-cols-2 gap-4">
            <div><label className="lbl">Occupation *</label>
              <select className={sel} value={form.current_occupation} onChange={e => set('current_occupation', e.target.value)}>
                <option value="">Select</option>{OCCUPATIONS.map(o => <option key={o}>{o}</option>)}</select></div>
            <div><label className="lbl">Specialization *</label>
              <select className={sel} value={form.specialization} onChange={e => set('specialization', e.target.value)}>
                <option value="">Select</option>{SPECIALIZATIONS.map(o => <option key={o}>{o}</option>)}</select></div>
            <div><label className="lbl">Age bracket</label>
              <select className={sel} value={form.age_bracket} onChange={e => set('age_bracket', e.target.value)}>
                <option value="">Prefer not to say</option>{AGE_BRACKETS.map(o => <option key={o}>{o}</option>)}</select></div>
            <div><label className="lbl">City</label>
              <select className={sel} value={form.city} onChange={e => set('city', e.target.value)}>
                <option value="">Select</option>{CITIES.map(o => <option key={o}>{o}</option>)}</select></div>
            <div><label className="lbl">Country</label>
              <select className={sel} value={form.country} onChange={e => set('country', e.target.value)}>
                {COUNTRIES.map(o => <option key={o}>{o}</option>)}</select></div>
            <div><label className="lbl">How did you hear about us?</label>
              <select className={sel} value={form.how_did_you_hear} onChange={e => set('how_did_you_hear', e.target.value)}>
                <option value="">Select</option>{HOW_HEARD.map(o => <option key={o}>{o}</option>)}</select></div>
          </div>
          <Notice msg={msgs.profile} />
          <button className="btn-primary">Save profile</button>
        </form>

        <form onSubmit={savePrefs} className="bg-white border border-slate-200 rounded-2xl p-6 space-y-2">
          <h2 className="font-display font-bold text-navy">Communication preferences</h2>
          <p className="text-slate-500 text-xs">You're in control — we only contact you the ways you allow here.</p>
          <Toggle checked={prefs.email} onChange={v => setPrefs(p => ({ ...p, email: v }))} label="Emails about courses and offers" hint="Every email also has a one-click unsubscribe link." />
          <Toggle checked={prefs.calls} onChange={v => setPrefs(p => ({ ...p, calls: v }))} label="Phone calls from an advisor" hint="Only during working hours." />
          <Toggle checked={prefs.whatsapp} onChange={v => setPrefs(p => ({ ...p, whatsapp: v }))} label="WhatsApp messages" hint="Short updates about the courses you're interested in." />
          <div className="pt-2"><label className="lbl">Phone (for calls / WhatsApp)</label>
            <input className="inp" value={prefs.phone} onChange={e => setPrefs(p => ({ ...p, phone: e.target.value }))} placeholder="+91 98xxxxxxxx" /></div>
          <Notice msg={msgs.prefs} />
          <button className="btn-primary">Save preferences</button>
        </form>

        <form onSubmit={savePassword} className="bg-white border border-slate-200 rounded-2xl p-6 space-y-4">
          <h2 className="font-display font-bold text-navy">Change password</h2>
          <div className="grid sm:grid-cols-3 gap-4">
            <div><label className="lbl">Current</label><input type="password" required className="inp" value={pw.current_password} onChange={e => setPw(p => ({ ...p, current_password: e.target.value }))} /></div>
            <div><label className="lbl">New</label><input type="password" required minLength={6} className="inp" value={pw.new_password} onChange={e => setPw(p => ({ ...p, new_password: e.target.value }))} /></div>
            <div><label className="lbl">Confirm new</label><input type="password" required minLength={6} className="inp" value={pw.confirm} onChange={e => setPw(p => ({ ...p, confirm: e.target.value }))} /></div>
          </div>
          <Notice msg={msgs.pw} />
          <button className="btn-primary">Change password</button>
        </form>
      </div>
    </main>
  )
}
