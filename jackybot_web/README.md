# JackyBot Web Interface

A modern web interface for managing JackyBot Discord server settings with real-time updates.

## Features

- Discord OAuth2 authentication
- Real-time cog enable/disable per server
- Beautiful blue and gold themed UI
- WebSocket integration for live updates
- Responsive design with animated toggles
- Category-based navigation

## Setup

### Backend Setup

1. Navigate to the backend directory:
```bash
cd jackybot_web/backend
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment variables in the root `.env` file:
```env
DISCORD_CLIENT_ID=your_discord_client_id
DISCORD_CLIENT_SECRET=your_discord_client_secret
DISCORD_REDIRECT_URI=http://localhost:5000/auth/callback
FLASK_SECRET_KEY=your_secret_key_here
WEBSOCKET_PORT=5000
WEB_INTERFACE_URL=http://localhost:5000
```

4. Start the Flask backend:
```bash
python app.py
```

The backend will run on `http://localhost:5000`

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd jackybot_web/frontend
```

2. Install Node.js dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

The frontend will run on `http://localhost:5173`

### Discord OAuth2 Setup

1. Go to the [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your bot application
3. Navigate to OAuth2 > General
4. Add the redirect URI: `http://localhost:5000/auth/callback`
5. Copy the Client ID and Client Secret to your `.env` file

### Bot Integration

The bot automatically loads the `web_interface_listener` cog which:
- Connects to the Flask backend via WebSocket
- Listens for cog enable/disable events
- Enforces cog restrictions per server in real-time

Make sure to not disable the `web_interface_listener` cog in `bot.py`.

## Production Deployment

For production:

1. Update environment variables with production URLs
2. Build the frontend:
```bash
cd jackybot_web/frontend
npm run build
```

3. Serve the built files with a production server
4. Use a reverse proxy (nginx/Apache) for both backend and frontend
5. Enable HTTPS with SSL certificates
6. Update CORS origins in `backend/config.py`

## Architecture

- **Backend**: Flask + Flask-SocketIO for REST API and WebSocket
- **Frontend**: React 18 + Vite + Tailwind CSS
- **Bot Integration**: Discord.py cog with socketio client
- **Data Storage**: JSON files in `data/` directory

## API Endpoints

- `GET /api/cogs` - List all available cogs
- `GET /api/servers` - List user's Discord servers
- `GET /api/servers/<id>/settings` - Get cog settings for a server
- `POST /api/servers/<id>/settings` - Update cog settings
- `GET /auth/login` - Start Discord OAuth2 flow
- `GET /auth/callback` - OAuth2 callback handler
- `GET /auth/user` - Get current user info
- `POST /auth/logout` - Logout current user

## WebSocket Events

- `connect` - Client connected
- `disconnect` - Client disconnected
- `cog_update` - Cog setting changed (broadcasted to all clients and bot)

