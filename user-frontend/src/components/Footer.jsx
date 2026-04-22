import { Link } from 'react-router-dom'
export default function Footer() {
  return (
    <footer className="bg-navy border-t border-white/10 text-slate-400 font-body">
      <div className="max-w-7xl mx-auto px-6 py-14 grid grid-cols-1 md:grid-cols-4 gap-10">
        <div>
          <div className="flex items-center gap-2 mb-4">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-sky-accent to-gold flex items-center justify-center font-display font-black text-navy text-lg">X</div>
            <span className="font-display font-bold text-white text-xl">Education</span>
          </div>
          <p className="text-sm leading-relaxed text-slate-500">Empowering industry professionals with world-class online education. 500,000+ learners. 40+ countries.</p>
        </div>
        <div>
          <h4 className="text-white font-semibold text-sm mb-4 font-display">Popular Courses</h4>
          <ul className="space-y-2 text-sm">
            {['Data Science & Analytics','Digital Marketing','MBA Core','Finance & Banking','HR Management'].map(c => (
              <li key={c}><Link to="/courses" className="hover:text-sky-accent transition-colors">{c}</Link></li>
            ))}
          </ul>
        </div>
        <div>
          <h4 className="text-white font-semibold text-sm mb-4 font-display">Company</h4>
          <ul className="space-y-2 text-sm">
            {['About Us','Careers','Blog','Press','Contact'].map(i => <li key={i}><span className="hover:text-sky-accent cursor-pointer">{i}</span></li>)}
          </ul>
        </div>
        <div>
          <h4 className="text-white font-semibold text-sm mb-4 font-display">Contact</h4>
          <ul className="space-y-3 text-sm">
            <li>📍 Andheri East, Mumbai 400069</li>
            <li>📞 +91 98765 43210</li>
            <li>✉️ admissions@xeducation.in</li>
            <li>🕐 Mon–Sat, 9 AM – 8 PM IST</li>
          </ul>
        </div>
      </div>
      <div className="border-t border-white/10 px-6 py-5 flex flex-col md:flex-row items-center justify-between gap-3 text-xs text-slate-600">
        <p>© {new Date().getFullYear()} X Education. All rights reserved.</p>
        <p>Privacy Policy · Terms of Use · Cookie Policy</p>
      </div>
    </footer>
  )
}
