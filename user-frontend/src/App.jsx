import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { useEffect } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import { tracker }          from './utils/tracker'
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

function ScrollTop() {
  const { pathname } = useLocation()
  useEffect(() => window.scrollTo(0, 0), [pathname])
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
  const { sessionId } = useAuth()
  useEffect(() => { if (sessionId) tracker.setSession(sessionId) }, [sessionId])
  return (
    <>
      <ScrollTop />
      <Navbar />
      <Routes>
        <Route path="/"                 element={<Home />} />
        <Route path="/courses"          element={<Courses />} />
        <Route path="/courses/:slug"    element={<CourseDetail />} />
        <Route path="/login"            element={<Login />} />
        <Route path="/signup"           element={<Signup />} />
        <Route path="/complete-profile" element={<Protected><CompleteProfile /></Protected>} />
        <Route path="/dashboard"        element={<Protected><UserDashboard /></Protected>} />
        <Route path="/cart"             element={<Protected><Cart /></Protected>} />
        <Route path="/wishlist"         element={<Protected><Wishlist /></Protected>} />
        <Route path="/checkout"         element={<Protected><Checkout /></Protected>} />
        <Route path="/enquiry/:slug"    element={<Protected><Enquiry /></Protected>} />
        <Route path="/thank-you"        element={<ThankYou />} />
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
