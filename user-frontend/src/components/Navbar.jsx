import { useState, useEffect } from 'react'
import { Link, useNavigate, useLocation } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'
import { getCart } from '../utils/api'

export default function Navbar() {
  const { user, logout } = useAuth()
  const [scrolled,  setScrolled]  = useState(false)
  const [open,      setOpen]      = useState(false)
  const [cartCount, setCartCount] = useState(0)
  const navigate = useNavigate()
  const location = useLocation()

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 40)
    window.addEventListener('scroll', fn)
    return () => window.removeEventListener('scroll', fn)
  }, [])

  useEffect(() => {
    if (user) getCart().then(r => setCartCount(r.data.cart.length)).catch(() => {})
  }, [user, location.pathname])

  const navLinks = [{ to: '/', label: 'Home' }, { to: '/courses', label: 'Courses' }]
  const act = to => location.pathname === to
    ? 'text-sky-accent font-semibold'
    : 'text-slate-300 hover:text-white'

  return (
    <nav className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300
      ${scrolled ? 'bg-navy shadow-xl py-3' : 'bg-navy/90 backdrop-blur-md py-5'}`}>
      <div className="max-w-7xl mx-auto px-6 flex items-center justify-between">

        {/* Logo */}
        <Link to="/" className="flex items-center gap-2">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-sky-accent to-gold
                          flex items-center justify-center font-display font-black text-navy text-lg">X</div>
          <span className="font-display font-bold text-white text-xl tracking-tight">Education</span>
        </Link>

        {/* Desktop nav */}
        <div className="hidden md:flex items-center gap-8">
          {navLinks.map(l => (
            <Link key={l.to} to={l.to} className={`font-body text-sm transition-colors ${act(l.to)}`}>
              {l.label}
            </Link>
          ))}
        </div>

        {/* Desktop actions */}
        <div className="hidden md:flex items-center gap-3">
          {user ? (
            <>
              {/* Wishlist icon */}
              <Link to="/wishlist" title="Saved Courses"
                className="p-2 text-slate-400 hover:text-white transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"/>
                </svg>
              </Link>
              {/* Cart icon */}
              <Link to="/cart" title="Cart" className="relative p-2 text-slate-400 hover:text-white transition-colors">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M3 3h2l.4 2M7 13h10l4-8H5.4M7 13L5.4 5M7 13l-2.293 2.293c-.63.63-.184 1.707.707 1.707H17m0 0a2 2 0 100 4 2 2 0 000-4zm-8 2a2 2 0 11-4 0 2 2 0 014 0z"/>
                </svg>
                {cartCount > 0 && (
                  <span className="absolute top-0 right-0 w-4 h-4 bg-ember rounded-full text-white
                                   text-xs flex items-center justify-center leading-none">
                    {cartCount}
                  </span>
                )}
              </Link>
              {/* Dashboard link */}
              <Link to="/dashboard"
                className="text-slate-300 hover:text-white text-sm border border-white/20
                           hover:border-white/50 px-4 py-2 rounded-xl transition-all">
                {user.name.split(' ')[0]}
              </Link>
              <button onClick={() => { logout(); navigate('/') }}
                className="text-slate-500 hover:text-slate-300 text-sm transition-colors">
                Sign out
              </button>
            </>
          ) : (
            <>
              <Link to="/login" className="text-slate-300 hover:text-white text-sm transition-colors">
                Login
              </Link>
              <Link to="/signup"
                className="bg-ember hover:bg-orange-600 text-white font-semibold text-sm
                           px-5 py-2.5 rounded-xl transition-all active:scale-95">
                Get Started
              </Link>
            </>
          )}
        </div>

        {/* Mobile hamburger */}
        <button className="md:hidden text-white p-1" onClick={() => setOpen(!open)}>
          <div className="space-y-1.5">
            <span className={`block w-6 h-0.5 bg-white transition-all ${open ? 'rotate-45 translate-y-2' : ''}`} />
            <span className={`block w-6 h-0.5 bg-white transition-all ${open ? 'opacity-0' : ''}`} />
            <span className={`block w-6 h-0.5 bg-white transition-all ${open ? '-rotate-45 -translate-y-2' : ''}`} />
          </div>
        </button>
      </div>

      {/* Mobile menu */}
      {open && (
        <div className="md:hidden bg-navy border-t border-white/10 px-6 py-4 space-y-1">
          {navLinks.map(l => (
            <Link key={l.to} to={l.to} onClick={() => setOpen(false)}
              className={`block text-sm py-2.5 border-b border-white/5 ${act(l.to)}`}>{l.label}
            </Link>
          ))}
          {user ? (
            <>
              <Link to="/wishlist"  onClick={() => setOpen(false)} className="block text-slate-300 text-sm py-2.5 border-b border-white/5">Saved Courses</Link>
              <Link to="/cart"      onClick={() => setOpen(false)} className="block text-slate-300 text-sm py-2.5 border-b border-white/5">Cart {cartCount > 0 && `(${cartCount})`}</Link>
              <Link to="/dashboard" onClick={() => setOpen(false)} className="block text-slate-300 text-sm py-2.5 border-b border-white/5">Dashboard</Link>
              <button onClick={() => { logout(); setOpen(false); navigate('/') }}
                className="block text-red-400 text-sm py-2.5 w-full text-left">Sign out</button>
            </>
          ) : (
            <>
              <Link to="/login"  onClick={() => setOpen(false)} className="block text-slate-300 text-sm py-2.5">Login</Link>
              <Link to="/signup" onClick={() => setOpen(false)}
                className="block mt-2 bg-ember text-white font-semibold text-sm text-center px-4 py-2.5 rounded-xl">
                Get Started
              </Link>
            </>
          )}
        </div>
      )}
    </nav>
  )
}