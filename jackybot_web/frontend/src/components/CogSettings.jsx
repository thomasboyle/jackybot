import { useState, useEffect } from 'react'
import ToggleSwitch from './ToggleSwitch'
import RoleManagementModal from './RoleManagementModal'
import TextChatModal from './TextChatModal'
import { api } from '../api/client'

function CogSettings({ serverId, cogs, selectedCategory, socket }) {
  const [settings, setSettings] = useState({})
  const [loading, setLoading] = useState(true)
  const [updatingCog, setUpdatingCog] = useState(null)
  const [selectedCog, setSelectedCog] = useState(null)
  const [modals, setModals] = useState({ roleManagement: false, textChat: false })

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

  const handleCogClick = (cog) => {
    if (!cog.clickable) return;

    if (cog.moderation_feature && !cog.requires_text_chat) {
      setSelectedCog(cog);
      setModals({ roleManagement: true, textChat: false });
    } else if (cog.requires_text_chat || cog.moderation_feature) {
      setSelectedCog(cog);
      setModals({ roleManagement: false, textChat: true });
    }
  };

  const closeModals = () => {
    setModals({ roleManagement: false, textChat: false });
    setSelectedCog(null);
  };

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

          return (
            <div
              key={cog.name}
              className={`card hover:shadow-xl transition-shadow duration-200 ${
                cog.clickable ? 'cursor-pointer' : ''
              }`}
              onClick={() => handleCogClick(cog)}
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
                    onChange={(newState) => handleToggle(cog.name, isEnabled)}
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

      {selectedCog && (
        <>
          {modals.roleManagement && (
            <RoleManagementModal
              isOpen={modals.roleManagement}
              onClose={closeModals}
              serverId={serverId}
              cog={selectedCog}
            />
          )}
          {modals.textChat && (
            <TextChatModal
              isOpen={modals.textChat}
              onClose={closeModals}
              serverId={serverId}
              cog={selectedCog}
            />
          )}
        </>
      )}
    </div>
  )
}

export default CogSettings

