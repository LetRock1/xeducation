import { useEffect, useState } from 'react'
import { scheduleCampaign, getCampaigns, deleteCampaign } from '../utils/api'

const TIERS = [
  'Target Immediately',
  'Nurture via Email/WhatsApp',
  'Marketing Campaign',
  'Low Priority',
]

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([])
  const [form, setForm] = useState({
    name: '', tier: 'Nurture via Email/WhatsApp',
    subject: '', body: '', scheduled_at: '',
  })
  const [busy,     setBusy]     = useState(false)
  const [deleting, setDeleting] = useState(null)
  const [msg,      setMsg]      = useState('')

  const load = () =>
    getCampaigns()
      .then(r => setCampaigns(r.data.campaigns))
      .catch(() => {})

  useEffect(() => { load() }, [])

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  async function submit(e) {
    e.preventDefault(); setBusy(true); setMsg('')
    try {
      await scheduleCampaign(form)
      setMsg('Campaign scheduled successfully.')
      setForm(f => ({ ...f, name: '', subject: '', body: '', scheduled_at: '' }))
      load()
    } catch (err) {
      setMsg('Error: ' + (err.response?.data?.detail || 'Failed to schedule'))
    } finally {
      setBusy(false)
    }
  }

  async function remove(id) {
    if (!window.confirm('Delete this campaign?')) return
    setDeleting(id)
    try {
      await deleteCampaign(id)
      load()
    } catch {
      alert('Failed to delete campaign.')
    } finally {
      setDeleting(null)
    }
  }

  const tierLabel = t =>
    t === 'Nurture via Email/WhatsApp' ? 'Nurture'
    : t === 'Marketing Campaign' ? 'Campaign'
    : t

  return (
    <div>
      <h1 className="font-display text-2xl font-bold text-white mb-6">Campaign Scheduler</h1>

      <div className="grid lg:grid-cols-2 gap-6">

        {/* Schedule form */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-white mb-5">Schedule New Campaign</h3>
          <form onSubmit={submit} className="space-y-4">
            <div>
              <label className="lbl">Campaign Name *</label>
              <input required value={form.name} onChange={e => set('name', e.target.value)}
                placeholder="e.g. March Nurture Batch" className="inp" />
            </div>
            <div>
              <label className="lbl">Target Tier *</label>
              <select required value={form.tier} onChange={e => set('tier', e.target.value)} className="inp">
                {TIERS.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div>
              <label className="lbl">Email Subject *</label>
              <input required value={form.subject} onChange={e => set('subject', e.target.value)}
                placeholder="Subject line for this campaign" className="inp" />
            </div>
            <div>
              <label className="lbl">Email Body *</label>
              <textarea required value={form.body} onChange={e => set('body', e.target.value)}
                rows={6}
                placeholder="Write the email body here. Use {name}, {course}, {coupon} as placeholders."
                className="inp font-mono text-xs" />
            </div>
            <div>
              <label className="lbl">Schedule Date & Time *</label>
              <input type="datetime-local" required value={form.scheduled_at}
                onChange={e => set('scheduled_at', e.target.value)} className="inp" />
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
              {busy ? 'Scheduling…' : 'Schedule Campaign'}
            </button>
          </form>
        </div>

        {/* Campaigns list */}
        <div className="card p-6">
          <h3 className="font-display font-semibold text-white mb-5">
            Scheduled Campaigns
            <span className="ml-2 text-slate-500 font-body font-normal text-sm">
              ({campaigns.length})
            </span>
          </h3>

          {!campaigns.length ? (
            <p className="text-slate-500 text-sm text-center py-10">
              No campaigns scheduled yet.
            </p>
          ) : (
            <div className="space-y-3 max-h-[520px] overflow-y-auto pr-1">
              {campaigns.map(c => (
                <div key={c.id}
                  className="bg-white/5 border border-white/10 rounded-xl p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <p className="font-semibold text-white text-sm truncate">{c.name}</p>
                        <span className={`flex-shrink-0 text-xs px-2 py-0.5 rounded-full ${
                          c.sent
                            ? 'bg-green-900/30 text-green-400'
                            : 'bg-yellow-900/30 text-yellow-400'}`}>
                          {c.sent ? 'Sent' : 'Scheduled'}
                        </span>
                      </div>
                      <p className="text-slate-400 text-xs mb-0.5">
                        Tier: {tierLabel(c.tier)}
                      </p>
                      <p className="text-slate-500 text-xs">
                        {new Date(c.scheduled_at).toLocaleString('en-IN', {
                          day: 'numeric', month: 'short', year: 'numeric',
                          hour: '2-digit', minute: '2-digit'
                        })}
                      </p>
                      <p className="text-slate-600 text-xs mt-1 truncate">
                        {c.subject}
                      </p>
                    </div>
                    {!c.sent && (
                      <button
                        onClick={() => remove(c.id)}
                        disabled={deleting === c.id}
                        className="p-1.5 text-slate-600 hover:text-red-400 hover:bg-red-900/20
                                   rounded-lg transition-all flex-shrink-0 disabled:opacity-50"
                        title="Delete campaign">
                        {deleting === c.id ? (
                          <div className="w-4 h-4 border-2 border-slate-500 border-t-transparent rounded-full animate-spin" />
                        ) : (
                          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                              d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"/>
                          </svg>
                        )}
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
