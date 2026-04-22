import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { useState } from 'react'
import Login     from './pages/Login'
import Dashboard from './pages/Dashboard'
import Leads     from './pages/Leads'
import LeadDetail from './pages/LeadDetail'
import Campaigns from './pages/Campaigns'
import Coupons   from './pages/Coupons'
import QnAPage   from './pages/QnAPage'
import Sidebar   from './components/Sidebar'

function Protected({ children }) {
  const token = localStorage.getItem('mkt_token')
  if (!token) return <Navigate to="/login" replace />
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex-1 ml-60 p-8 overflow-auto">
        {children}
      </div>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login"      element={<Login />} />
        <Route path="/"           element={<Protected><Dashboard /></Protected>} />
        <Route path="/leads"      element={<Protected><Leads /></Protected>} />
        <Route path="/leads/:id"  element={<Protected><LeadDetail /></Protected>} />
        <Route path="/campaigns"  element={<Protected><Campaigns /></Protected>} />
        <Route path="/coupons"    element={<Protected><Coupons /></Protected>} />
        <Route path="/qna"        element={<Protected><QnAPage /></Protected>} />
      </Routes>
    </BrowserRouter>
  )
}
