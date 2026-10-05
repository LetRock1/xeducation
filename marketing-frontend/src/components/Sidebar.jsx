import { NavLink, useNavigate } from 'react-router-dom'

const links = [
  { to:'/',          icon:'📊', label:'Dashboard'  },
  { to:'/copilot',   icon:'💬', label:'Ask the CRM' },
  { to:'/learning',  icon:'🔁', label:'Learning loop' },
  { to:'/actions',   icon:'⚡', label:"Today's actions" },
  { to:'/leads',     icon:'🎯', label:'Leads'       },
  { to:'/pipeline',  icon:'🗂️', label:'Pipeline'    },
  { to:'/journeys',  icon:'🧭', label:'Journeys'    },
  { to:'/callbacks', icon:'📞', label:'Callbacks'   },
  { to:'/campaigns', icon:'📅', label:'Campaigns'   },
  { to:'/ab-tests',  icon:'🧪', label:'A/B Tests'   },
  { to:'/coupons',   icon:'🎟️', label:'Coupons'     },
  { to:'/qna',       icon:'❓', label:'Q&A'         },
]

export default function Sidebar() {
  const navigate = useNavigate()
  function logout() { localStorage.removeItem('mkt_token'); navigate('/login') }

  return (
    <aside className="fixed left-0 top-0 bottom-0 w-60 bg-navy border-r border-white/10 flex flex-col z-40">
      <div className="px-6 py-6 border-b border-white/10">
        <div className="flex items-center gap-2 mb-1">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-sky-accent to-gold flex items-center justify-center font-display font-black text-navy text-sm">X</div>
          <span className="font-display font-bold text-white text-sm">Education CRM</span>
        </div>
        <p className="text-slate-500 text-xs">Learns · tests · acts</p>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-1">
        {links.map(l => (
          <NavLink key={l.to} to={l.to} end={l.to==='/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-all
               ${isActive ? 'bg-ember text-white shadow-lg shadow-ember/20' : 'text-slate-400 hover:text-white hover:bg-white/5'}`}>
            <span className="text-base leading-none">{l.icon}</span>{l.label}
          </NavLink>
        ))}
      </nav>

      <div className="px-3 py-4 border-t border-white/10">
        <button onClick={logout} className="w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm text-slate-500 hover:text-red-400 hover:bg-white/5 transition-all">
          <span className="text-base leading-none">🚪</span> Logout
        </button>
      </div>
    </aside>
  )
}
