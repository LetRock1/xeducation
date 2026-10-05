import { Link } from 'react-router-dom'

const SECTIONS = [
  ['What this site is',
    'X Education is a final-year student project: a course website connected to a CRM (customer relationship management system). It is not a real course provider. Payments are simulated and nothing is ever charged.'],
  ['What we record',
    'What you give us: your name, e-mail address, password (stored only as a hash), and, if you add them, your phone number, occupation, specialisation and city. What you do on this site: visits, pages and time on them, the course video, pricing, brochure, chat, wishlist, cart, checkout and enquiries. The e-mails we send you and whether you click them.'],
  ['Why',
    'To estimate how likely you are to buy a course, to choose the next step for you (an e-mail, a coupon, a call from an advisor, a WhatsApp message, or nothing), and to measure which messages work. 5% of learners are picked at random to receive no automatic messages at all, so we can measure what the messages change.'],
  ['Who sees it',
    'Only the project team, in the marketing dashboard. It is not sold or shared. E-mails are sent through Gmail. If the AI writing assistant is switched on, your first name, occupation, specialisation and the course are sent to Google Gemini to draft a message.'],
  ['Your choices',
    'In Settings you can stop e-mails, calls or WhatsApp messages; every e-mail has an unsubscribe link. Settings → Delete my account removes your account and everything recorded about you.'],
]

export default function Privacy() {
  return (
    <main className="min-h-screen bg-slate-50 pt-24 pb-16">
      <div className="max-w-2xl mx-auto px-6">
        <h1 className="font-display text-3xl font-extrabold text-navy mb-2">Privacy notice</h1>
        <p className="text-slate-500 text-sm mb-8">In plain words: what this site records about you, and why.</p>
        <div className="bg-white border border-slate-200 rounded-2xl p-8 space-y-6">
          {SECTIONS.map(([title, text]) => (
            <section key={title}>
              <h2 className="font-display font-bold text-navy mb-1">{title}</h2>
              <p className="text-slate-600 text-sm leading-relaxed">{text}</p>
            </section>
          ))}
        </div>
        <p className="text-slate-500 text-sm mt-6">
          <Link to="/settings" className="text-sky-accent hover:underline">Settings</Link> ·{' '}
          <Link to="/" className="text-sky-accent hover:underline">Home</Link>
        </p>
      </div>
    </main>
  )
}
