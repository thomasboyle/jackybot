# JackyBot Web Interface - Project Structure

```
jackybot_web/
│
├── backend/                          # Flask Backend
│   ├── app.py                        # Main Flask app with OAuth2 & WebSocket
│   ├── config.py                     # Configuration management
│   ├── cog_manager.py                # Cog settings CRUD operations
│   └── requirements.txt              # Python dependencies
│
├── frontend/                         # React Frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── Dashboard.jsx         # Main dashboard layout
│   │   │   ├── LoginPage.jsx         # Discord OAuth2 login page
│   │   │   ├── VerticalNav.jsx       # Left sidebar navigation
│   │   │   ├── ServerSelector.jsx    # Server dropdown selector
│   │   │   ├── CogSettings.jsx       # Cog toggle grid
│   │   │   └── ToggleSwitch.jsx      # Animated toggle component
│   │   ├── api/
│   │   │   └── client.js             # API client functions
│   │   ├── styles/
│   │   │   └── index.css             # Tailwind CSS with custom styles
│   │   ├── App.jsx                   # Root component with routing
│   │   └── main.jsx                  # React entry point
│   │
│   ├── index.html                    # HTML template
│   ├── package.json                  # Node.js dependencies
│   ├── vite.config.js                # Vite configuration
│   ├── tailwind.config.js            # Tailwind CSS config (blue/gold theme)
│   └── postcss.config.js             # PostCSS configuration
│
├── start_backend.bat / .sh           # Backend startup scripts
├── start_frontend.bat / .sh          # Frontend startup scripts
├── env_example.txt                   # Environment variables template
├── SETUP_GUIDE.md                    # Step-by-step setup instructions
├── README.md                         # Project overview and documentation
└── PROJECT_STRUCTURE.md              # This file

Related files in main project:
│
├── cogs/
│   └── cog_metadata.json             # Cog metadata for web UI
│
├── data/
│   └── cog_settings.json             # Server-specific cog settings storage
│
├── requirements.txt                  # Updated with python-socketio
└── .env                              # Environment variables (add web config)
```

## Data Flow

### 1. User Authentication
```
User → Frontend → Flask (/auth/login) → Discord OAuth2 → Flask (/auth/callback) → Frontend (dashboard)
```

### 2. Loading Settings
```
Frontend → Flask (/api/servers) → Discord API → Frontend (server list)
Frontend → Flask (/api/cogs) → cog_metadata.json → Frontend (cog list)
Frontend → Flask (/api/servers/:id/settings) → cog_settings.json → Frontend (current settings)
```

### 3. Updating Settings
```
User toggles cog → Frontend → Flask (/api/servers/:id/settings) → cog_settings.json
                                     ↓
                            WebSocket broadcast
                                     ↓
                        ┌────────────┴────────────┐
                        ↓                         ↓
                  Bot (listener)            All Frontend Clients
                  Updates in-memory         Update UI immediately
                  Enforces restrictions
```

### 4. Command Execution
```
Discord User → Command → Bot → Cog Execution
                                       ↓
                          ┌────────────┴────────────┐
                          ↓                         ↓
                    Enabled: Execute          Disabled: Deny
```

## Key Features

### Backend (Flask)
- **OAuth2 Authentication**: Secure Discord login
- **REST API**: CRUD operations for cog settings
- **WebSocket Server**: Real-time updates broadcast
- **Session Management**: Secure user sessions
- **CORS Configuration**: Frontend integration

### Frontend (React)
- **Modern UI**: React 18 with hooks
- **Real-time Updates**: Socket.io client
- **Responsive Design**: Mobile-friendly
- **Animated Components**: Smooth transitions
- **Theme**: Blue (#3B82F6) and Gold (#F59E0B)

### Bot Integration
- **Dynamic Cog Control**: Enable/disable per server
- **Persistent Storage**: JSON-based configuration

## Color Scheme

- **Primary Blue**: #3B82F6 (buttons, active states)
- **Gold Accent**: #F59E0B (highlights, gradients)
- **Dark Background**: #1E293B (main background)
- **Dark Light**: #334155 (cards, panels)
- **Dark Lighter**: #475569 (borders, hover states)

## Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + Vite + Tailwind CSS |
| Backend | Flask + Flask-SocketIO + Python 3.8+ |
| Bot | Discord.py + python-socketio |
| Storage | JSON files |
| Auth | Discord OAuth2 |
| Real-time | WebSocket (Socket.io) |

