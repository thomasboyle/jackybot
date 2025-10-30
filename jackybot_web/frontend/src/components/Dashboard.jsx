import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { io } from 'socket.io-client'
import VerticalNav from './VerticalNav'
import ServerSelector from './ServerSelector'
import CogSettings from './CogSettings'
import { api } from '../api/client'

function Dashboard({ user, onLogout }) {
  const navigate = useNavigate()
  const [servers, setServers] = useState([])
  const [selectedServer, setSelectedServer] = useState(null)
  const [cogs, setCogs] = useState([])
  const [selectedCategory, setSelectedCategory] = useState('All')
  const [socket, setSocket] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadInitialData()
    
    const socketUrl = import.meta.env.DEV ? 'http://localhost:5000' : undefined
    const socketInstance = io(socketUrl, {
      withCredentials: true,
      transports: ['websocket', 'polling'],
      path: '/socket.io'
    })
    
    socketInstance.on('connect', () => {
      console.log('Connected to WebSocket')
    })
    
    setSocket(socketInstance)
    
    return () => {
      socketInstance.disconnect()
    }
  }, [])

  const loadInitialData = async () => {
    try {
      setLoading(true)
      const [serversData, cogsData] = await Promise.all([
        api.getServers(),
        api.getCogs()
      ])
      
      setServers(serversData)
      setCogs(cogsData)
      
      if (serversData.length > 0) {
        setSelectedServer(serversData[0].id)
      }
    } catch (error) {
      console.error('Failed to load data:', error)
      if (error.status === 401) {
        console.warn('Authentication failed, redirecting to login')
        navigate('/login')
      }
    } finally {
      setLoading(false)
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-xl">Loading dashboard...</div>
      </div>
    )
  }

  return (
    <div className="flex min-h-screen">
      <VerticalNav
        cogs={cogs}
        selectedCategory={selectedCategory}
        onSelectCategory={setSelectedCategory}
      />
      
      <div className="flex-1 flex flex-col">
        <header className="bg-dark-light border-b border-dark-lighter p-4">
          <div className="flex items-center justify-between">
            <ServerSelector
              servers={servers}
              selectedServer={selectedServer}
              onSelectServer={setSelectedServer}
            />
            
            <div className="flex items-center gap-4">
              {user && (
                <div className="flex items-center gap-2">
                  {user.avatar && (
                    <img
                      src={`https://cdn.discordapp.com/avatars/${user.id}/${user.avatar}.png`}
                      alt={user.username}
                      className="w-8 h-8 rounded-full"
                    />
                  )}
                  <span className="text-sm font-medium">{user.username}</span>
                </div>
              )}
              <button
                onClick={onLogout}
                className="text-sm text-gray-400 hover:text-white transition-colors"
              >
                Logout
              </button>
            </div>
          </div>
        </header>
        
        <main className="flex-1 p-6 overflow-y-auto">
          {selectedServer ? (
            <CogSettings
              serverId={selectedServer}
              cogs={cogs}
              selectedCategory={selectedCategory}
              socket={socket}
            />
          ) : (
            <div className="flex items-center justify-center h-64">
              <div className="text-center">
                <p className="text-xl text-gray-400">No servers available</p>
                <p className="text-sm text-gray-500 mt-2">
                  Make sure the bot is in your server and you have admin permissions
                </p>
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}

export default Dashboard

