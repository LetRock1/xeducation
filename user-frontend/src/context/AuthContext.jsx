import { createContext, useContext, useState, useEffect } from 'react'
import axios from 'axios'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user,    setUser]    = useState(null)
  const [profile, setProfile] = useState(null)
  const [token,   setToken]   = useState(() => localStorage.getItem('xe_token'))
  const [loading, setLoading] = useState(true)
  const [sessionId, setSessionId] = useState(() => Number(localStorage.getItem('xe_sid')) || null)

  useEffect(() => {
    if (token) {
      axios.defaults.headers.common['Authorization'] = `Bearer ${token}`
      axios.get('/api/auth/me')
        .then(r => { setUser(r.data.user); setProfile(r.data.profile) })
        .catch(() => logout())
        .finally(() => setLoading(false))
    } else {
      delete axios.defaults.headers.common['Authorization']
      setLoading(false)
    }
  }, [token])

  function login(tok, userData, sid) {
    localStorage.setItem('xe_token', tok)
    if (sid) { localStorage.setItem('xe_sid', sid); setSessionId(sid) }
    setToken(tok)
    setUser(userData)
    axios.defaults.headers.common['Authorization'] = `Bearer ${tok}`
  }

  function logout() {
    localStorage.removeItem('xe_token')
    localStorage.removeItem('xe_sid')
    setToken(null); setUser(null); setProfile(null); setSessionId(null)
    delete axios.defaults.headers.common['Authorization']
  }

  function refreshProfile() {
    axios.get('/api/auth/me').then(r => setProfile(r.data.profile)).catch(() => {})
  }

  return (
    <AuthContext.Provider value={{ user, profile, token, loading, sessionId, login, logout, refreshProfile }}>
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => useContext(AuthContext)
