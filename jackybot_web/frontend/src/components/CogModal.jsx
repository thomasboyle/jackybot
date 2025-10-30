import { useState, useEffect } from 'react'
import { api } from '../api/client'

function CogModal({ cog, serverId, isOpen, onClose }) {
  const [channelExists, setChannelExists] = useState(null)
  const [loading, setLoading] = useState(false)

  const channelMapping = {
    'freegames': 'free-games',
    'zen_updates': 'zen-updates',
    'steamos_updates': 'steamos-updates'
  }

  const requiredChannel = channelMapping[cog?.name]

  useEffect(() => {
    if (isOpen && serverId && requiredChannel) {
      checkChannel()
    } else {
      setChannelExists(null)
    }
  }, [isOpen, serverId, requiredChannel])

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

          {requiredChannel && (
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
          )}
        </div>
      </div>
    </div>
  )
}

export default CogModal

