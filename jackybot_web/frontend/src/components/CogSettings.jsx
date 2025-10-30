import { useState, useEffect } from 'react'
import ToggleSwitch from './ToggleSwitch'
import CogModal from './CogModal'
import { api } from '../api/client'

function CogSettings({ serverId, cogs, selectedCategory, socket }) {
  const [settings, setSettings] = useState({})
  const [loading, setLoading] = useState(true)
  const [updatingCog, setUpdatingCog] = useState(null)
  const [selectedCog, setSelectedCog] = useState(null)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const specialCogs = ['freegames', 'zen_updates', 'steamos_updates']

  useEffect(() => {
    if (serverId) {
      loadSettings()
    }
  }, [serverId])

  useEffect(() => {
    if (socket) {
      socket.on('cog_update', handleCogUpdate)
      return () => socket.off('cog_update', handleCogUpdate)
    }
  }, [socket])

  const handleCogUpdate = (data) => {
    if (data.server_id === serverId) {
      setSettings(prev => ({
        ...prev,
        [data.cog_name]: { enabled: data.enabled }
      }))
    }
  }

  const loadSettings = async () => {
    try {
      setLoading(true)
      const serverSettings = await api.getServerSettings(serverId)
      setSettings(serverSettings)
    } catch (error) {
      console.error('Failed to load settings:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleToggle = async (cogName, currentState) => {
    setUpdatingCog(cogName)
    try {
      await api.updateServerSettings(serverId, cogName, !currentState)
      setSettings(prev => ({
        ...prev,
        [cogName]: { enabled: !currentState }
      }))
    } catch (error) {
      console.error('Failed to update setting:', error)
    } finally {
      setUpdatingCog(null)
    }
  }

  const handleCardClick = (cog) => {
    if (specialCogs.includes(cog.name)) {
      setSelectedCog(cog)
      setIsModalOpen(true)
    }
  }

  const closeModal = () => {
    setIsModalOpen(false)
    setSelectedCog(null)
  }

  const filteredCogs = selectedCategory === 'All' 
    ? cogs 
    : cogs.filter(cog => cog.category === selectedCategory)

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-xl">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">
          {selectedCategory === 'All' ? 'All Cogs' : `${selectedCategory} Cogs`}
        </h2>
        <div className="text-sm text-gray-400">
          {filteredCogs.length} cog{filteredCogs.length !== 1 ? 's' : ''}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {filteredCogs.map((cog) => {
          const isEnabled = settings[cog.name]?.enabled ?? true
          const isUpdating = updatingCog === cog.name
          const isSpecialCog = specialCogs.includes(cog.name)

          return (
            <div
              key={cog.name}
              className={`card hover:shadow-xl transition-shadow duration-200 ${
                isSpecialCog ? 'cog-card-glint cog-card-glint-clickable' : ''
              }`}
              onClick={() => handleCardClick(cog)}
            >
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-3">
                  <span className="text-3xl">{cog.icon}</span>
                  <div>
                    <h3 className="font-semibold text-lg">{cog.display_name}</h3>
                    <span className="text-xs text-gray-400">{cog.category}</span>
                  </div>
                </div>
                <div onClick={(e) => e.stopPropagation()}>
                  <ToggleSwitch
                    enabled={isEnabled}
                    onChange={() => handleToggle(cog.name, isEnabled)}
                    disabled={isUpdating}
                  />
                </div>
              </div>
              <p className="text-sm text-gray-400">
                {cog.description}
              </p>
              {isUpdating && (
                <div className="mt-2 text-xs text-primary animate-pulse">
                  Updating...
                </div>
              )}
            </div>
          )
        })}
      </div>

      <CogModal
        cog={selectedCog}
        serverId={serverId}
        isOpen={isModalOpen}
        onClose={closeModal}
      />
    </div>
  )
}

export default CogSettings

