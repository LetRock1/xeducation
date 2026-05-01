import { useLocation, Link } from 'react-router-dom'

export default function ThankYou() {
  const { state } = useLocation()
  const { name, purchased, discount } = state || {}
  const first = name?.split(' ')[0] || 'there'

  // ── Purchase confirmation (checkout flow) ──────────────────────────────────
  if (purchased) {
    return (
      <main className="min-h-screen bg-slate-50 pt-20 pb-16 flex items-center">
        <div className="max-w-xl mx-auto px-6 text-center">
          <div className="w-20 h-20 bg-green-100 border-2 border-green-400 rounded-full
                          flex items-center justify-center mx-auto mb-6">
            <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          </div>
          <h1 className="font-display text-3xl font-extrabold text-navy mb-2">
            Purchase Successful
          </h1>
          <p className="text-slate-500 mb-6">
            Welcome to X Education, {first}. Your courses are now active.
          </p>
          <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-6 text-left">
            <p className="font-semibold text-navy text-sm mb-3">Courses Enrolled</p>
            <div className="space-y-2">
              {purchased.map(c => (
                <div key={c} className="flex items-center gap-2 text-sm text-slate-700">
                  <svg className="w-4 h-4 text-green-500 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                  </svg>
                  {c}
                </div>
              ))}
            </div>
            {discount && discount !== 'None' && (
              <p className="text-green-700 text-sm mt-3 pt-3 border-t border-slate-100">
                Discount applied: {discount}
              </p>
            )}
          </div>
          <div className="flex flex-col sm:flex-row gap-3 justify-center">
            <Link to="/dashboard"
              className="bg-ember hover:bg-orange-600 text-white font-semibold px-6 py-3 rounded-xl transition-all">
              Go to Dashboard
            </Link>
            <Link to="/courses"
              className="border-2 border-slate-200 text-slate-600 font-semibold px-6 py-3 rounded-xl hover:border-navy hover:text-navy transition-all">
              Browse More Courses
            </Link>
          </div>
        </div>
      </main>
    )
  }

  // ── Enquiry confirmation ───────────────────────────────────────────────────
  return (
    <main className="min-h-screen bg-slate-50 pt-20 pb-16 flex items-center">
      <div className="max-w-xl mx-auto px-6 text-center">

        {/* Check icon */}
        <div className="w-20 h-20 bg-green-100 border-2 border-green-400 rounded-full
                        flex items-center justify-center mx-auto mb-6">
          <svg className="w-10 h-10 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
          </svg>
        </div>

        <h1 className="font-display text-3xl font-extrabold text-navy mb-2">
          Enquiry Received
        </h1>
        <p className="text-slate-500 mb-8">
          Thank you, {first}. Our team will review your profile and reach out shortly.
        </p>

        {/* What happens next */}
        <div className="bg-white border border-slate-200 rounded-2xl p-6 mb-8 text-left">
          <h3 className="font-display font-bold text-navy text-sm mb-4 uppercase tracking-wide">
            What Happens Next
          </h3>
          <div className="space-y-4">
            {[
              {
                step: '1',
                title: 'Profile reviewed',
                desc: 'Our admissions team reviews your background and course match.',
                time: 'Right now',
              },
              {
                step: '2',
                title: 'Personalised email',
                desc: 'You will receive detailed course information and next steps.',
                time: 'Within 1 hour',
              },
              {
                step: '3',
                title: 'Advisor call',
                desc: 'An advisor will call you to answer any questions you have.',
                time: 'Within 2 hours',
              },
            ].map(({ step, title, desc, time }) => (
              <div key={step} className="flex gap-4">
                <div className="w-8 h-8 rounded-full bg-ember flex items-center
                                justify-center text-white font-bold text-sm flex-shrink-0">
                  {step}
                </div>
                <div>
                  <p className="font-semibold text-navy text-sm">{title}</p>
                  <p className="text-slate-500 text-xs mt-0.5">{desc}</p>
                  <p className="text-slate-400 text-xs mt-0.5">{time}</p>
                </div>
              </div>
            ))}
          </div>
        </div>

        <div className="flex flex-col sm:flex-row gap-3 justify-center">
          <Link to="/dashboard"
            className="bg-ember hover:bg-orange-600 text-white font-semibold px-6 py-3 rounded-xl transition-all">
            My Dashboard
          </Link>
          <Link to="/courses"
            className="border-2 border-slate-200 text-slate-600 font-semibold px-6 py-3 rounded-xl hover:border-navy hover:text-navy transition-all">
            Browse More Courses
          </Link>
        </div>
      </div>
    </main>
  )
}