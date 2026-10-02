import { useParams, Link } from 'react-router-dom'
import { getCourseBySlug } from '../data/courses'

// Printable course brochure. "Download PDF" uses the browser's Save-as-PDF,
// so no PDF library is needed and the brochure always matches the course data.
export default function Brochure() {
  const { slug } = useParams()
  const c = getCourseBySlug(slug)
  if (!c) return <main className="pt-28 text-center text-slate-600">Course not found.</main>

  return (
    <main className="min-h-screen bg-slate-100 pt-24 pb-16 print:pt-0 print:bg-white">
      <div className="no-print max-w-3xl mx-auto px-6 mb-4 flex justify-between items-center">
        <Link to={`/courses/${slug}`} className="text-sm text-slate-500 hover:text-navy">← Back to course</Link>
        <button onClick={() => window.print()} className="btn-primary text-sm">Download PDF</button>
      </div>
      <article className="max-w-3xl mx-auto bg-white shadow-sm print:shadow-none rounded-2xl print:rounded-none overflow-hidden">
        <header className="bg-navy text-white px-10 py-10">
          <p className="text-sky-accent font-display font-bold tracking-wide text-sm">X EDUCATION · PROGRAMME BROCHURE</p>
          <h1 className="font-display text-4xl font-extrabold mt-3">{c.title}</h1>
          <p className="text-slate-300 mt-2 text-lg">{c.tagline}</p>
          <div className="flex flex-wrap gap-6 mt-6 text-sm">
            <span><b className="text-gold">Duration</b> {c.duration}</span>
            <span><b className="text-gold">Level</b> {c.level}</span>
            <span><b className="text-gold">Fee</b> ₹{c.price.toLocaleString()} · EMI ₹{c.emi.toLocaleString()}/mo</span>
          </div>
        </header>
        <section className="px-10 py-8 grid sm:grid-cols-2 gap-8">
          <div>
            <h2 className="font-display font-bold text-navy text-lg mb-3">What you'll gain</h2>
            <ul className="space-y-2 text-slate-700 text-sm list-disc pl-5">{c.outcomes.map(o => <li key={o}>{o}</li>)}</ul>
          </div>
          <div>
            <h2 className="font-display font-bold text-navy text-lg mb-3">Your instructor</h2>
            <p className="font-semibold text-navy">{c.instructor.name}</p>
            <p className="text-slate-600 text-sm">{c.instructor.role}</p>
            <p className="text-slate-500 text-sm">{c.instructor.exp} of experience</p>
          </div>
        </section>
        <section className="px-10 pb-8">
          <h2 className="font-display font-bold text-navy text-lg mb-3">Curriculum</h2>
          <ol className="space-y-2">
            {c.curriculum.map((m, i) => (
              <li key={m.w} className="flex gap-4 items-start border border-slate-100 rounded-xl px-4 py-3">
                <span className="w-7 h-7 shrink-0 rounded-full bg-navy text-white text-xs font-bold flex items-center justify-center">{i + 1}</span>
                <span><span className="block text-xs text-slate-400 uppercase tracking-wide">{m.w}</span>
                  <span className="text-slate-800 text-sm font-medium">{m.t}</span></span>
              </li>
            ))}
          </ol>
        </section>
        <div className="px-10 py-6 bg-slate-50 text-xs text-slate-500 flex justify-between">
          <span>Online · self-paced with weekly live doubt sessions</span>
          <span>xeducation · {new Date().getFullYear()}</span>
        </div>
      </article>
    </main>
  )
}
