import { useLocation, useNavigate, Link } from 'react-router-dom'

const TIER = {
  'Target Immediately':         { icon:'🔴', label:'Priority Lead',     msg:"Expect a call from our senior advisor within 30 minutes. You're a top match.",                   bg:'bg-red-50 border-red-200',    c:'text-red-600'   },
  'Nurture via Email/WhatsApp': { icon:'🟠', label:'High Potential',    msg:"A personalised Success Blueprint is on its way to your email. Check it in the next hour.",       bg:'bg-orange-50 border-orange-200', c:'text-orange-600'},
  'Marketing Campaign':         { icon:'🟡', label:'Interested Lead',   msg:"We've added you to our upcoming webinar list. Check your email for the invite.",                  bg:'bg-yellow-50 border-yellow-200', c:'text-yellow-700'},
  'Low Priority':               { icon:'🟢', label:'Explorer',          msg:"We'll keep you updated with our monthly knowledge digest. No pressure — just great content.",     bg:'bg-green-50 border-green-200', c:'text-green-600' },
}

export default function ThankYou() {
  const { state }   = useLocation()
  const navigate    = useNavigate()
  const { name, score, action, purchased, discount } = state || {}
  const tier        = TIER[action] || TIER['Low Priority']
  const first       = name?.split(' ')[0] || 'there'
  const s           = score ?? 0

  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16 flex items-center">
      <div className="max-w-xl mx-auto px-6 text-center">
        {/* Purchased mode */}
        {purchased ? (
          <>
            <div className="w-24 h-24 rounded-full bg-green-100 border-4 border-green-400 flex items-center justify-center text-4xl mx-auto mb-6">🎉</div>
            <h1 className="font-display text-4xl font-extrabold text-navy mb-3">Purchase Successful!</h1>
            <p className="text-slate-500 mb-6">Welcome to X Education, {first}! Your courses are now unlocked.</p>
            <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6 text-left">
              <p className="font-semibold text-navy mb-3">Courses Enrolled:</p>
              {purchased.map(c => <p key={c} className="text-slate-700 text-sm flex items-center gap-2 mb-1"><span className="text-green-500">✓</span>{c}</p>)}
              {discount && discount !== 'None' && <p className="text-green-600 text-sm mt-3 font-semibold">✓ Discount applied: {discount}</p>}
            </div>
          </>
        ) : (
          <>
            <div className="w-24 h-24 rounded-full bg-green-100 border-4 border-green-400 flex items-center justify-center text-4xl mx-auto mb-6">✓</div>
            <h1 className="font-display text-4xl font-extrabold text-navy mb-3">You're all set, {first}!</h1>
            <p className="text-slate-500 mb-6">Your enquiry has been received. Here's what happens next.</p>

            {/* Lead score */}
            {s > 0 && (
              <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-5 shadow-sm">
                <p className="text-slate-400 text-sm uppercase tracking-widest mb-3">Your Profile Match Score</p>
                <div className="relative w-28 h-28 mx-auto mb-4">
                  <svg viewBox="0 0 36 36" className="w-full h-full -rotate-90">
                    <circle cx="18" cy="18" r="15.9" fill="none" stroke="#e2e8f0" strokeWidth="3"/>
                    <circle cx="18" cy="18" r="15.9" fill="none"
                      stroke={s>=80?'#f97316':s>=60?'#f59e0b':'#64748b'}
                      strokeWidth="3" strokeDasharray={`${s} ${100-s}`} strokeLinecap="round"/>
                  </svg>
                  <div className="absolute inset-0 flex flex-col items-center justify-center">
                    <span className="font-display text-2xl font-extrabold text-navy">{s}</span>
                    <span className="text-slate-400 text-xs">/100</span>
                  </div>
                </div>
                <div className={`rounded-xl border px-4 py-3 ${tier.bg}`}>
                  <p className={`font-semibold ${tier.c} mb-1`}>{tier.icon} {tier.label}</p>
                  <p className="text-slate-600 text-sm">{tier.msg}</p>
                </div>
              </div>
            )}

            {/* Next steps */}
            <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6 text-left shadow-sm">
              <h3 className="font-display font-bold text-navy mb-4">What Happens Next</h3>
              {[
                { step:'1', text:'Our team reviews your profile and course match.', time:'Right now' },
                { step:'2', text:'You receive a personalised email with course details and a special offer.', time:'Within 1 hour' },
                { step:'3', text:'An advisor calls you if you provided a phone number.', time:'Within 2 hours' },
              ].map(({ step, text, time }) => (
                <div key={step} className="flex gap-4 mb-4 last:mb-0">
                  <div className="w-8 h-8 rounded-full bg-ember flex items-center justify-center text-white font-bold text-sm flex-shrink-0">{step}</div>
                  <div>
                    <p className="text-slate-700 text-sm">{text}</p>
                    <p className="text-slate-400 text-xs mt-0.5">{time}</p>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link to="/courses" className="btn-outline">Browse More Courses</Link>
          <Link to="/dashboard" className="btn-primary">My Dashboard</Link>
        </div>
      </div>
    </main>
  )
}
