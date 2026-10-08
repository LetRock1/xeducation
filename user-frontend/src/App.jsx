import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { useEffect } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import { tracker, captureSource } from './utils/tracker'
import { emailClick } from './utils/api'
import Navbar               from './components/Navbar'
import Footer               from './components/Footer'
import ChatWidget           from './components/ChatWidget'
import Home                 from './pages/Home'
import Courses              from './pages/Courses'
import CourseDetail         from './pages/CourseDetail'
import Login                from './pages/Login'
import Signup               from './pages/Signup'
import CompleteProfile      from './pages/CompleteProfile'
import UserDashboard        from './pages/UserDashboard'
import Cart                 from './pages/Cart'
import Wishlist             from './pages/Wishlist'
import Checkout             from './pages/Checkout'
import Enquiry              from './pages/Enquiry'
import ThankYou             from './pages/ThankYou'
import ForgotPassword       from './pages/ForgotPassword'
import Settings             from './pages/Settings'
import Brochure             from './pages/Brochure'
import Privacy              from './pages/Privacy'
import Unsubscribe          from './pages/Unsubscribe'

captureSource()   // remember utm_source / referrer of the landing page

function ScrollTop() {
  const { pathname } = useLocation()
  const { user } = useAuth()
  useEffect(() => { window.scrollTo(0, 0) }, [pathname])
  // time-on-page tracking for every page (feeds TotalTimeOnWebsite / PageViewsPerVisit)
  useEffect(() => {
    if (!user) return
    const m = pathname.match(/^\/courses\/([^/]+)/)
    tracker.pageChange(m ? m[1] : null)
  }, [pathname, user])
  return null
}

/* Someone clicked "View Course" in one of our emails: the link is the course page with ?ref=<email token>.
   Report the click once (it is tied to that exact email and re-scores the learner), then tidy the address bar. */
function EmailRef() {
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  useEffect(() => {
    const params = new URLSearchParams(search)
    const ref = params.get('ref')
    if (!ref) return
    const key = `xe_ref_${ref}`
    let seen = false
    try { seen = !!sessionStorage.getItem(key); sessionStorage.setItem(key, '1') } catch { /* storage blocked */ }
    if (!seen) emailClick(ref).catch(() => {})
    params.delete('ref')
    const rest = params.toString()
    navigate({ pathname, search: rest ? `?${rest}` : '' }, { replace: true })
  }, [pathname, search, navigate])
  return null
}

function Protected({ children }) {
  const { user, loading } = useAuth()
  if (loading) return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="w-8 h-8 border-4 border-ember border-t-transparent rounded-full animate-spin" />
    </div>
  )
  if (!user) return <Navigate to="/login" replace />
  return children
}

function AppShell() {
  return (
    <>
      <ScrollTop />
      <EmailRef />
      <Navbar />
      <Routes>
        <Route path="/"                 element={<Home />} />
        <Route path="/courses"          element={<Courses />} />
        <Route path="/courses/:slug"    element={<CourseDetail />} />
        <Route path="/courses/:slug/brochure" element={<Protected><Brochure /></Protected>} />
        <Route path="/forgot-password"  element={<ForgotPassword />} />
        <Route path="/settings"         element={<Protected><Settings /></Protected>} />
        <Route path="/login"            element={<Login />} />
        <Route path="/signup"           element={<Signup />} />
        <Route path="/complete-profile" element={<Protected><CompleteProfile /></Protected>} />
        <Route path="/dashboard"        element={<Protected><UserDashboard /></Protected>} />
        <Route path="/cart"             element={<Protected><Cart /></Protected>} />
        <Route path="/wishlist"         element={<Protected><Wishlist /></Protected>} />
        <Route path="/checkout"         element={<Protected><Checkout /></Protected>} />
        <Route path="/enquiry/:slug"    element={<Protected><Enquiry /></Protected>} />
        <Route path="/thank-you"        element={<ThankYou />} />
        <Route path="/privacy"          element={<Privacy />} />
        <Route path="/unsubscribe"      element={<Unsubscribe />} />
      </Routes>
      <Footer />
      <ChatWidget />
    </>
  )
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </AuthProvider>
  )
}
