import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import LoginPage from './components/LoginPage'
import Dashboard from './components/Dashboard'
import CompressPage from './components/CompressPage'
import { api } from './api/client'

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [isLoading, setIsLoading] = useState(true)
  const [user, setUser] = useState(null)

  useEffect(() => {
    checkAuth()
  }, [])

  const checkAuth = async () => {
    try {
      const userData = await api.getCurrentUser()
      setUser(userData)
      setIsAuthenticated(true)
    } catch (error) {
      setIsAuthenticated(false)
      setUser(null)
      if (error.status === 401) {
        console.warn('Session expired or not authenticated')
      }
    } finally {
      setIsLoading(false)
    }
  }

  const handleLogout = async () => {
    try {
      await api.logout()
      setIsAuthenticated(false)
      setUser(null)
    } catch (error) {
      console.error('Logout failed:', error)
    }
  }

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-xl">Loading...</div>
      </div>
    )
  }

  return (
    <Router>
      <Routes>
        <Route 
          path="/login" 
          element={
            isAuthenticated ? 
            <Navigate to="/dashboard" replace /> : 
            <LoginPage onLogin={() => setIsAuthenticated(true)} />
          } 
        />
        <Route
          path="/dashboard"
          element={
            isAuthenticated ?
            <Dashboard user={user} onLogout={handleLogout} /> :
            <Navigate to="/login" replace />
          }
        />
        <Route
          path="/compress"
          element={
            isAuthenticated ?
            <CompressPage user={user} onLogout={handleLogout} /> :
            <Navigate to="/login" replace />
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  )
}

export default App

