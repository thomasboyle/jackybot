# JackyBot Server Setup Guide

This guide will walk you through deploying JackyBot on your Hetzner Ubuntu server using Docker.

## Prerequisites

- Ubuntu server (20.04 or newer recommended)
- SSH access to your server
- Git installed
- At least 16GB RAM (8GB minimum for CPU inference)
- 50GB+ free disk space (for models and cache)

## Initial Server Setup

### 1. Install Docker and Docker Compose

SSH into your Hetzner server and run:

```bash
# Update package list
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y apt-transport-https ca-certificates curl software-properties-common

# Add Docker's official GPG key
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add your user to docker group (to run docker without sudo)
sudo usermod -aG docker $USER

# Log out and back in for group changes to take effect
```

Verify Docker installation:
```bash
docker --version
docker compose version
```

### 2. Clone the Repository

```bash
# Navigate to your preferred directory
cd ~

# Clone the repository
git clone https://github.com/yourusername/jackybot.git

# Navigate into the project
cd jackybot
```

### 3. Configure Environment Variables

```bash
# Copy the example environment file
cp env.example .env

# Edit the .env file with your credentials
nano .env
```

Add your actual credentials:
- `Discord_Bot_Token`: Get from https://discord.com/developers/applications
- `GROQ_API_KEY`: Get from https://console.groq.com/keys

Save and exit (Ctrl+X, then Y, then Enter)

### 4. Initial Deployment

Make the deploy script executable:
```bash
chmod +x deploy.sh
```

Build and start the bot:
```bash
docker compose build
docker compose up -d
```

The first run will take significant time as it downloads all models (~10GB+).

## Managing the Bot

### View Logs

```bash
# Follow logs in real-time
docker compose logs -f

# View last 100 lines
docker compose logs --tail=100

# View logs for specific timeframe
docker compose logs --since 1h
```

### Check Status

```bash
docker compose ps
```

### Restart the Bot

```bash
docker compose restart
```

### Stop the Bot

```bash
docker compose down
```

### Update the Bot

```bash
# Run the deployment script
./deploy.sh
```

Or manually:
```bash
git pull
docker compose build --no-cache
docker compose down
docker compose up -d
```

### Access Container Shell

```bash
docker compose exec jackybot bash
```

## Resource Monitoring

Monitor Docker container resources:
```bash
docker stats jackybot
```

Monitor system resources:
```bash
# Install htop if not available
sudo apt install htop

# Run htop
htop
```

## Persistent Data

The following directories are persisted outside the container:
- `./data/` - Bot data (command stats, user data, etc.)
- `./json/` - Configuration files
- `./cache/` - Downloaded AI models
- `./assets/` - Images and videos

These directories will persist even when the container is rebuilt.

## Troubleshooting

### Bot Won't Start

Check logs for errors:
```bash
docker compose logs --tail=100
```

Common issues:
- Invalid Discord token or Groq API key
- Insufficient memory (requires at least 8GB)
- Missing environment variables

### Out of Memory Errors

If you encounter OOM errors, adjust resource limits in `docker-compose.yml`:
```yaml
deploy:
  resources:
    limits:
      memory: 12G  # Increase if needed
```

### Models Not Loading

Ensure you have enough disk space:
```bash
df -h
```

Models are cached in `./cache/` and can be large (10GB+).

### Container Keeps Restarting

Check logs and ensure:
- Environment variables are set correctly
- Required ports are not in use
- Sufficient system resources available

## Security Recommendations

1. Keep your `.env` file secure (never commit to Git)
2. Regularly update the server:
   ```bash
   sudo apt update && sudo apt upgrade -y
   ```
3. Consider setting up a firewall:
   ```bash
   sudo ufw allow ssh
   sudo ufw enable
   ```
4. Use SSH keys instead of passwords for server access

## Performance Optimization

### CPU-Only Inference
This deployment uses CPU inference. Image generation will be slower than GPU but fully functional.

Expected performance:
- Image generation: 30-120 seconds per image (depending on model)
- Text responses: Near-instant (via Groq API)
- Audio processing: 5-20 seconds

### Resource Allocation
Adjust CPU/memory limits in `docker-compose.yml` based on your server specs:
- Minimum: 2 CPUs, 4GB RAM
- Recommended: 4 CPUs, 8GB RAM
- Optimal: 8+ CPUs, 16GB+ RAM

## Backup and Maintenance

### Backup Important Data

```bash
# Create backup directory
mkdir -p ~/backups

# Backup data and configuration
tar -czf ~/backups/jackybot-backup-$(date +%Y%m%d).tar.gz data/ json/ .env

# Optional: backup cache (large files)
tar -czf ~/backups/jackybot-cache-$(date +%Y%m%d).tar.gz cache/
```

### Restore from Backup

```bash
cd ~/jackybot
tar -xzf ~/backups/jackybot-backup-YYYYMMDD.tar.gz
```

### Regular Maintenance

1. Monitor disk usage
2. Review logs periodically
3. Keep Docker and system packages updated
4. Restart bot weekly to clear memory if needed

## Additional Commands

```bash
# Remove old Docker images
docker image prune -a

# View disk usage by Docker
docker system df

# Clean up unused Docker resources
docker system prune -a

# Rebuild without cache
docker compose build --no-cache

# View environment variables (without values)
docker compose config
```

## Getting Help

If you encounter issues:
1. Check logs: `docker compose logs -f`
2. Verify environment variables in `.env`
3. Check system resources: `htop` and `df -h`
4. Review Discord bot permissions in Discord Developer Portal

## Next Steps

After successful deployment:
1. Test bot commands in your Discord server
2. Monitor performance and adjust resources if needed
3. Set up automated backups
4. Consider adding monitoring/alerting (optional)

