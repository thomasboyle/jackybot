# VPS Setup Guide - Quick Start

## Automated Setup

Run the setup script on your VPS:

```bash
cd jackybot_web
chmod +x setup_vps.sh
./setup_vps.sh
```

The script will:
1. ✅ Install system dependencies (Python, Node.js, Nginx)
2. ✅ Set up Python virtual environment
3. ✅ Install Python dependencies
4. ✅ Install Node.js dependencies
5. ✅ Build frontend for production
6. ✅ Configure systemd service
7. ✅ Configure Nginx reverse proxy
8. ✅ Set up SSL certificate (optional)

## Manual Steps After Setup

### 1. Configure Environment Variables

Edit `.env` file in the project root:

```bash
nano ../.env
```

Required variables:
```env
DISCORD_CLIENT_ID=your_client_id_here
DISCORD_CLIENT_SECRET=your_client_secret_here
DISCORD_REDIRECT_URI=https://your-domain.com/auth/callback
FLASK_SECRET_KEY=$(openssl rand -hex 32)
WEB_INTERFACE_URL=https://your-domain.com
WEBSOCKET_PORT=5000
COG_SETTINGS_PATH=../data/cog_settings.json
COG_METADATA_PATH=../cogs/cog_metadata.json
```

### 2. Update Discord OAuth2 Settings

1. Go to [Discord Developer Portal](https://discord.com/developers/applications)
2. Select your application
3. Navigate to **OAuth2 > General**
4. Add redirect URI: `https://your-domain.com/auth/callback`
5. Save changes

### 3. Start Services

```bash
sudo systemctl start jackybot-web-backend
sudo systemctl enable jackybot-web-backend
sudo systemctl restart nginx
```

### 4. Check Status

```bash
sudo systemctl status jackybot-web-backend
sudo systemctl status nginx
```

### 5. View Logs

```bash
sudo journalctl -u jackybot-web-backend -f
```

## Firewall Configuration

If using UFW:

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 22/tcp
sudo ufw enable
```

## Troubleshooting

### Backend won't start
```bash
# Check logs
sudo journalctl -u jackybot-web-backend -n 50

# Check if port is in use
sudo netstat -tlnp | grep 5000

# Verify environment variables
cd jackybot_web/backend
source venv/bin/activate
python -c "from config import Config; print(Config.DISCORD_CLIENT_ID)"
```

### Nginx errors
```bash
# Test configuration
sudo nginx -t

# Check error logs
sudo tail -f /var/log/nginx/error.log

# Reload Nginx
sudo systemctl reload nginx
```

### Frontend not loading
- Verify frontend was built: `ls -la jackybot_web/frontend/dist`
- Check Nginx configuration points to correct directory
- Verify file permissions: `sudo chown -R www-data:www-data jackybot_web/frontend/dist`

### WebSocket connection fails
- Check backend is running: `sudo systemctl status jackybot-web-backend`
- Verify `/socket.io` location in Nginx config
- Check firewall allows WebSocket connections

## Service Management

```bash
# Start
sudo systemctl start jackybot-web-backend

# Stop
sudo systemctl stop jackybot-web-backend

# Restart
sudo systemctl restart jackybot-web-backend

# Enable on boot
sudo systemctl enable jackybot-web-backend

# Disable on boot
sudo systemctl disable jackybot-web-backend

# Status
sudo systemctl status jackybot-web-backend

# Logs (follow)
sudo journalctl -u jackybot-web-backend -f

# Logs (last 100 lines)
sudo journalctl -u jackybot-web-backend -n 100
```

## Updating the Web UI

After making changes:

```bash
cd jackybot_web/backend
source venv/bin/activate
pip install -r requirements.txt

cd ../frontend
npm install
npm run build

sudo systemctl restart jackybot-web-backend
sudo systemctl reload nginx
```

## Security Checklist

- [ ] SSL certificate installed and working
- [ ] `.env` file has secure `FLASK_SECRET_KEY`
- [ ] File permissions set correctly (no 777)
- [ ] Firewall configured (only 80, 443, 22 open)
- [ ] Discord OAuth2 redirect URI matches exactly
- [ ] Backend runs on localhost (127.0.0.1), not public IP
- [ ] Nginx properly configured as reverse proxy
- [ ] Regular backups of `data/cog_settings.json`

## Access URLs

- **Web Interface**: `https://your-domain.com`
- **API Endpoint**: `https://your-domain.com/api`
- **Backend Status**: Check `sudo systemctl status jackybot-web-backend`

## Support Files

- `setup_vps.sh` - Main setup script
- `start_services.sh` - Quick start script
- `stop_services.sh` - Quick stop script

