import { useState, useEffect } from 'react'
import { api } from '../api/client'

function CogModal({ cog, serverId, isOpen, onClose }) {
  const [channelExists, setChannelExists] = useState(null)
  const [loading, setLoading] = useState(false)

  // Highlights-specific state
  const [channels, setChannels] = useState([])
  const [currentChannel, setCurrentChannel] = useState('')
  const [selectedChannel, setSelectedChannel] = useState('')
  const [loadingChannels, setLoadingChannels] = useState(false)
  const [updatingChannel, setUpdatingChannel] = useState(false)

  const channelMapping = {
    'freegames': 'free-games',
    'zen_updates': 'zen-updates',
    'steamos_updates': 'steamos-updates'
  }

  const requiredChannel = channelMapping[cog?.name]

  useEffect(() => {
    if (isOpen && serverId) {
      if (cog?.name === 'highlights') {
        loadHighlightsData()
      } else if (requiredChannel) {
        checkChannel()
      }
    } else {
      // Reset all state when modal closes
      setChannelExists(null)
      setChannels([])
      setCurrentChannel('')
      setSelectedChannel('')
      setLoadingChannels(false)
      setUpdatingChannel(false)
    }
  }, [isOpen, serverId, requiredChannel, cog])

  const checkChannel = async () => {
    if (!serverId || !requiredChannel) {
      setChannelExists(null)
      return
    }

    setLoading(true)
    try {
      const result = await api.checkChannelExists(serverId, requiredChannel)
      setChannelExists(result.exists)
    } catch (error) {
      console.error('Failed to check channel:', error)
      setChannelExists(false)
    } finally {
      setLoading(false)
    }
  }

  const loadHighlightsData = async () => {
    if (!serverId) return

    setLoadingChannels(true)
    try {
      // Load available channels
      const channelsData = await api.getServerChannels(serverId)
      setChannels(channelsData)

      // Load current highlights channel
      const currentChannelData = await api.getHighlightsChannel(serverId)
      const channelName = currentChannelData.channel_name
      setCurrentChannel(channelName || '')
      setSelectedChannel(channelName || '')
    } catch (error) {
      console.error('Failed to load highlights data:', error)
      setChannels([])
      setCurrentChannel('')
      setSelectedChannel('')
    } finally {
      setLoadingChannels(false)
    }
  }

  const updateHighlightsChannel = async (channelName) => {
    if (!serverId) return

    setUpdatingChannel(true)
    try {
      await api.setHighlightsChannel(serverId, channelName)
      setCurrentChannel(channelName)
    } catch (error) {
      console.error('Failed to update highlights channel:', error)
      // Revert selection on error
      setSelectedChannel(currentChannel)
    } finally {
      setUpdatingChannel(false)
    }
  }

  const handleChannelChange = (e) => {
    const newChannelName = e.target.value
    setSelectedChannel(newChannelName)
    if (newChannelName !== currentChannel) {
      updateHighlightsChannel(newChannelName)
    }
  }

  if (!isOpen || !cog) return null

  const extractUsage = (description) => {
    if (description.includes('Automatic - no command needed')) {
      return 'Automatic - no command needed'
    }
    const usageMatch = description.match(/Usage:\s*(.+?)(?:\.|$)/i)
    return usageMatch ? usageMatch[1].trim() : 'N/A'
  }

  const usage = extractUsage(cog.description)

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black bg-opacity-50" onClick={onClose}>
      <div className="bg-dark-light rounded-lg p-6 max-w-md w-full mx-4 shadow-2xl" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <span className="text-4xl">{cog.icon}</span>
            <h2 className="text-2xl font-bold">{cog.display_name}</h2>
          </div>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-white transition-colors text-2xl font-bold"
          >
            ×
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <span className="text-xs text-gray-400 uppercase tracking-wide">Category</span>
            <p className="text-lg mt-1">{cog.category}</p>
          </div>

          <div>
            <span className="text-xs text-gray-400 uppercase tracking-wide">Description</span>
            <p className="text-sm text-gray-300 mt-1">{cog.description}</p>
          </div>

          <div>
            <span className="text-xs text-gray-400 uppercase tracking-wide">Usage</span>
            <p className="text-sm text-gray-300 mt-1 font-mono">{usage}</p>
          </div>

          {cog.name === 'highlights' ? (
            <div>
              <span className="text-xs text-gray-400 uppercase tracking-wide">Highlights Channel</span>
              <div className="mt-2 space-y-3">
                <div>
                  <label className="block text-sm text-gray-300 mb-1">Select Channel:</label>
                  {loadingChannels ? (
                    <div className="text-sm text-gray-400">Loading channels...</div>
                  ) : (
                    <select
                      value={selectedChannel}
                      onChange={handleChannelChange}
                      disabled={updatingChannel}
                      className="w-full bg-dark-light border border-gray-600 rounded px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                    >
                      <option value="">Select a channel...</option>
                      {channels.map(channel => (
                        <option key={channel.id} value={channel.name}>
                          #{channel.name}
                        </option>
                      ))}
                    </select>
                  )}
                  {updatingChannel && (
                    <div className="text-xs text-primary mt-1">Updating...</div>
                  )}
                </div>

                {currentChannel && (
                  <div>
                    <span className="text-xs text-gray-400 uppercase tracking-wide">Current Channel</span>
                    <div className="flex items-center gap-2 mt-2">
                      <span className="text-sm text-gray-300">
                        Channel <code className="bg-dark px-2 py-1 rounded">#{currentChannel}</code>{' '}
                        {channels.some(ch => ch.name === currentChannel) ? 'exists' : 'does not exist'}
                      </span>
                    </div>
                  </div>
                )}
              </div>
            </div>
          ) : (
            requiredChannel && (
              <div>
                <span className="text-xs text-gray-400 uppercase tracking-wide">Required Channel</span>
                <div className="flex items-center gap-2 mt-2">
                  {loading ? (
                    <span className="text-sm text-gray-400">Checking...</span>
                  ) : (
                    <>
                      <span className={`text-2xl ${channelExists ? 'text-green-500' : 'text-red-500'}`}>
                        {channelExists ? '✓' : '✗'}
                      </span>
                      <span className="text-sm text-gray-300">
                        Channel <code className="bg-dark px-2 py-1 rounded">#{requiredChannel}</code>{' '}
                        {channelExists ? 'detected' : 'not found'}
                      </span>
                    </>
                  )}
                </div>
              </div>
            )
          )}
        </div>
      </div>
    </div>
  )
}

export default CogModal

