import { useState, useEffect, useRef } from 'react'

function ServerSelector({ servers, selectedServer, onSelectServer }) {
  const [isOpen, setIsOpen] = useState(false)
  const dropdownRef = useRef(null)

  useEffect(() => {
    const handleClickOutside = (event) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const currentServer = servers.find(s => s.id === selectedServer)

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center gap-3 bg-dark-light px-4 py-3 rounded-lg hover:bg-dark-lighter transition-colors w-full md:w-auto"
      >
        {currentServer && (
          <>
            {currentServer.icon ? (
              <img 
                src={`https://cdn.discordapp.com/icons/${currentServer.id}/${currentServer.icon}.png`}
                alt={currentServer.name}
                className="w-8 h-8 rounded-full"
              />
            ) : (
              <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-sm font-bold">
                {currentServer.name.charAt(0)}
              </div>
            )}
            <span className="font-semibold">{currentServer.name}</span>
          </>
        )}
        {!currentServer && <span>Select a server</span>}
        <svg
          className={`w-5 h-5 transition-transform ${isOpen ? 'rotate-180' : ''}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {isOpen && (
        <div className="absolute top-full left-0 mt-2 w-full md:w-80 bg-dark-light rounded-lg shadow-xl border border-dark-lighter z-50 max-h-96 overflow-y-auto">
          {servers.map((server) => (
            <button
              key={server.id}
              onClick={() => {
                onSelectServer(server.id)
                setIsOpen(false)
              }}
              className={`
                flex items-center gap-3 w-full px-4 py-3 hover:bg-dark-lighter transition-colors
                ${selectedServer === server.id ? 'bg-primary' : ''}
              `}
            >
              {server.icon ? (
                <img 
                  src={`https://cdn.discordapp.com/icons/${server.id}/${server.icon}.png`}
                  alt={server.name}
                  className="w-8 h-8 rounded-full"
                />
              ) : (
                <div className="w-8 h-8 rounded-full bg-primary flex items-center justify-center text-sm font-bold">
                  {server.name.charAt(0)}
                </div>
              )}
              <span className="font-semibold">{server.name}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default ServerSelector

