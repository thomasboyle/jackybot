# JackyBot Web Interface - Setup Guide

## Quick Start

Follow these steps to get the web interface running:

### Step 1: Configure Environment Variables

1. Copy the contents from `env_example.txt`
2. Add them to your root `.env` file (one level up from jackybot_web)
3. Fill in the required values:
   - Get `DISCORD_CLIENT_ID` and `DISCORD_CLIENT_SECRET` from Discord Developer Portal
   - Generate a random `FLASK_SECRET_KEY`

### Step 2: Set Up Discord OAuth2

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your bot application
3. Navigate to **OAuth2 > General**
4. Under "Redirects", add: `http://localhost:5000/auth/callback`
5. Save changes

### Step 3: Install Backend Dependencies

```bash
cd jackybot_web/backend
pip install -r requirements.txt
```

### Step 4: Install Frontend Dependencies

```bash
cd jackybot_web/frontend
npm install
```

### Step 5: Install Bot Dependencies

The bot needs `python-socketio` to communicate with the web interface:

```bash
cd ../..  # Back to root
pip install python-socketio[asyncio_client]==5.10.0
```

### Step 6: Start Everything

You need to run three things:

**Terminal 1 - Bot:**
```bash
python bot.py
```

**Terminal 2 - Backend:**
```bash
cd jackybot_web
./start_backend.bat  # Windows
# or
./start_backend.sh   # Linux/Mac
```

**Terminal 3 - Frontend:**
```bash
cd jackybot_web
./start_frontend.bat  # Windows
# or
./start_frontend.sh   # Linux/Mac
```

### Step 7: Access the Web Interface

1. Open your browser and go to: `http://localhost:5173`
2. Click "Login with Discord"
3. Authorize the application
4. You'll be redirected to the dashboard

## Features

- **Server Selection**: Choose which Discord server to configure
- **Category Navigation**: Browse cogs by category (AI, Music, Fun, etc.)
- **Toggle Switches**: Enable/disable cogs with animated switches
- **Real-time Updates**: Changes apply immediately across all clients
- **Beautiful UI**: Blue and gold themed interface

## Troubleshooting

### Backend won't start
- Check that port 5000 is not already in use
- Verify `.env` file has all required variables
- Check `data/` directory exists

### Frontend won't start
- Make sure you ran `npm install` in the frontend directory
- Check that port 5173 is available
- Try deleting `node_modules` and running `npm install` again

### OAuth redirect fails
- Verify the redirect URI in Discord Developer Portal matches exactly
- Check that DISCORD_CLIENT_ID and DISCORD_CLIENT_SECRET are correct
- Make sure backend is running on port 5000

### Bot not connecting to web interface
- Check that WEB_INTERFACE_URL in `.env` points to `http://localhost:5000`
- Verify the backend is running
- Check bot console for connection errors

### Cog toggles not working
- Ensure the bot is running and connected to the web interface
- Check that the server ID is correct
- Verify `data/cog_settings.json` is writable

## Architecture

```
┌─────────────┐         ┌──────────────┐         ┌─────────────┐
│   Browser   │ ◄─────► │    Flask     │ ◄─────► │ Discord Bot │
│  (React)    │  HTTP/  │   Backend    │ WebSocket│   (Python)  │
│             │  WS     │              │         │             │
└─────────────┘         └──────────────┘         └─────────────┘
                               │
                               ▼
                        ┌──────────────┐
                        │ cog_settings │
                        │    .json     │
                        └──────────────┘
```

## Next Steps

- Configure which cogs are enabled for each server
- Customize the theme colors in `frontend/tailwind.config.js`
- Set up production deployment with HTTPS
- Add more management features as needed

