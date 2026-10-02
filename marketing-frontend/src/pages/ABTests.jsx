import { useEffect, useState } from 'react'
import { createAbTest, getAbTests, sendAbTest, getAbTestResults } from '../utils/api'

const TIERS = [
  'All leads',
  'Target Immediately',
  'Nurture via Email/WhatsApp',
  'Marketing Campaign',
  'Low Priority',
]

export default function ABTests() {
  const [tests, setTests] = useState([])
  const [form, setForm] = useState({
    name: '', tier: 'Nurture via Email/WhatsApp',
    subject_a: '', body_a: '', subject_b: '', body_b: '',
  })
  const [busy, setBusy] = useState(false)
  const [sendingId, setSendingId] = useState(null)
  const [msg, setMsg] = useState('')
  const [results, setResults] = useState({})

  const load = () => getAbTests().then(r => setTests(r.data.ab_tests)).catch(() => {})
  useEffect(() => { load() }, [])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function submit(e) {
    e.preventDefault(); setBusy(true); setMsg('')
    try {
      await createAbTest(form)
      setMsg('A/B test created.')
      setForm(f => ({ ...f, name: '', subject_a: '', body_a: '', subject_b: '', body_b: '' }))
      load()
    } catch (err) {
      setMsg('Error: ' + (err.response?.data?.detail || 'Failed to create'))
    } finally { setBusy(false) }
  }

  async function send(id) {
    setSendingId(id)
    try {
      const r = await sendAbTest(id)
      setMsg(r.data.message)
      load()
    } catch (err) {
      setMsg('Error: ' + (err.response?.data?.detail || 'Failed to send'))
    } finally { setSendingId(null) }
  }

  async function loadResults(id) {
    try {
      const r = await getAbTestResults(id)
      setResults(res => ({ ...res, [id]: r.data }))
    } catch {}
  }

  const tierLabel = t => t === 'Nurture via Email/WhatsApp' ? 'Nurture' : t === 'Marketing Campaign' ? 'Campaign' : t

  return (
    <div>
      <h1 className="font-display text-2xl font-bold text-white mb-6">A/B Tests</h1>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Create form */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-white mb-5">Create New A/B Test</h3>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="lbl">Test Name *</label>
              <input required value={form.name} onChange={e => set('name', e.target.value)}
                placeholder="e.g. Subject line urgency test" className="inp" />
            </div>
            <div>
              <label className="lbl">Target Tier *</label>
              <select required value={form.tier} onChange={e => set('tier', e.target.value)} className="inp">
                {TIERS.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="lbl">Variant A Subject *</label>
                <input required value={form.subject_a} onChange={e => set('subject_a', e.target.value)} className="inp" />
              </div>
              <div>
                <label className="lbl">Variant B Subject *</label>
                <input required value={form.subject_b} onChange={e => set('subject_b', e.target.value)} className="inp" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="lbl">Variant A Body *</label>
                <textarea required value={form.body_a} onChange={e => set('body_a', e.target.value)} rows={5} className="inp font-mono text-xs" />
              </div>
              <div>
                <label className="lbl">Variant B Body *</label>
                <textarea required value={form.body_b} onChange={e => set('body_b', e.target.value)} rows={5} className="inp font-mono text-xs" />
              </div>
            </div>
            {msg && (
              <p className={`text-sm px-3 py-2 rounded-xl border ${
                msg.startsWith('Error')
                  ? 'text-red-400 bg-red-900/20 border-red-800/30'
                  : 'text-green-400 bg-green-900/20 border-green-800/30'}`}>
                {msg}
              </p>
            )}
            <button type="submit" disabled={busy} className="w-full btn">
              {busy ? 'Creating…' : 'Create A/B Test'}
            </button>
          </form>
        </div>

        {/* Tests list */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-white mb-5">
            Tests <span className="ml-2 text-slate-500 font-body font-normal text-sm">({tests.length})</span>
          </h3>
          {!tests.length ? (
            <p className="text-slate-500 text-sm text-center py-10">No A/B tests yet.</p>
          ) : (
            <div className="space-y-3 max-h-[560px] overflow-y-auto pr-1">
              {tests.map(t => (
                <div key={t.id} className="bg-white/5 border border-white/10 rounded-xl p-4">
                  <div className="flex items-center gap-2 mb-1">
                    <p className="font-semibold text-white text-sm truncate flex-1">{t.name}</p>
                    <span className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full ${
                      t.status === 'sent' ? 'bg-green-900/30 text-green-400' : 'bg-yellow-900/30 text-yellow-400'}`}>
                      {t.status === 'sent' ? 'Sent' : t.status === 'sending' ? 'Sending…' : 'Draft'}
                    </span>
                  </div>
                  <p className="text-slate-400 text-xs mb-2">Tier: {tierLabel(t.tier)}</p>

                  {t.status === 'sending' ? (
                    <p className="text-slate-500 text-xs text-center py-2">Sending in progress — refresh in a moment.</p>
                  ) : t.status !== 'sent' ? (
                    <button onClick={() => send(t.id)} disabled={sendingId === t.id}
                      className="w-full btn text-xs py-2 disabled:opacity-60">
                      {sendingId === t.id ? 'Sending…' : 'Send to Matching Leads'}
                    </button>
                  ) : !results[t.id] ? (
                    <button onClick={() => loadResults(t.id)} className="w-full btn text-xs py-2">
                      View Results
                    </button>
                  ) : (
                    <div>
                      <div className="grid grid-cols-2 gap-2 text-xs">
                        {['variant_a', 'variant_b'].map((v, i) => (
                          <div key={v} className={`rounded-lg p-2 border ${
                            results[t.id].winner === (i === 0 ? 'A' : 'B') ? 'border-ember bg-ember/10' : 'border-white/10 bg-white/5'}`}>
                            <p className="text-slate-300 font-semibold mb-1">Variant {i === 0 ? 'A' : 'B'}{results[t.id].winner === (i === 0 ? 'A' : 'B') && ' 🏆'}</p>
                            <p className="text-slate-500">Sent: {results[t.id][v].sent}</p>
                            <p className="text-slate-500">Clicked: {results[t.id][v].clicked} ({results[t.id][v].click_rate}%)</p>
                            <p className="text-slate-500">Bought within 14 days: {results[t.id][v].converted} ({results[t.id][v].conversion_rate}%)</p>
                          </div>
                        ))}
                      </div>
                      <p className="mt-2 text-slate-400 text-[11px] leading-snug">{results[t.id].verdict}</p>
                      {results[t.id].click_test?.p_value != null && (
                        <p className="text-slate-500 text-[11px]">
                          Click-rate difference (B − A): {(results[t.id].click_test.diff * 100).toFixed(1)} pts,
                          95% CI [{(results[t.id].click_test.ci_low * 100).toFixed(1)}, {(results[t.id].click_test.ci_high * 100).toFixed(1)}],
                          p = {results[t.id].click_test.p_value}
                        </p>
                      )}
                      <button onClick={() => loadResults(t.id)} className="mt-2 text-xs text-sky-accent hover:underline">Refresh</button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
